"""
Flashcard service — background deck generation and Leitner box review logic.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flashcard import Flashcard, FlashcardCardType, FlashcardDeck, FlashcardDeckStatus, FlashcardReview
from app.rag.base import QueryParam
from app.rag.utils import parse_json_robust, openai_llm_func
from app.services.quiz_service import _resolve_file_classroom

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEITNER_INTERVALS: dict[int, int] = {1: 0, 2: 1, 3: 3, 4: 7, 5: 14}
RAG_CHUNK_TOP_K = 25
DEDUP_FRONT_CAP = 100

_BROAD_SEED = (
    "All key terms, definitions, concepts, examples, and formulas in this document. "
    "Cover every major topic uniformly."
)

_VALID_TYPES = {"definition", "concept", "example", "formula"}

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class EmptyContextError(Exception):
    pass


class MalformedCardsError(Exception):
    pass


# ---------------------------------------------------------------------------
# RAG context retrieval
# ---------------------------------------------------------------------------

async def build_deck_context(engine: Any, file_url: str) -> tuple[str, dict]:
    """Retrieve broad file-scoped context for flashcard generation."""
    qp = QueryParam(
        mode="naive",
        only_need_context=True,
        file_filter=file_url,
        chunk_top_k=RAG_CHUNK_TOP_K,
    )
    result = await engine.aquery(_BROAD_SEED, qp)
    ctx = (result.content if result else "") or ""
    if not ctx.strip():
        raise EmptyContextError(
            "No content could be retrieved for this file. "
            "The file may not have been fully processed yet."
        )
    return ctx, {"context_chars": len(ctx), "chunk_top_k": RAG_CHUNK_TOP_K}


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

async def _collect_existing_fronts(db: AsyncSession, user_id: int, file_id: int) -> list[str]:
    result = await db.execute(
        select(Flashcard.front)
        .where(Flashcard.user_id == user_id, Flashcard.file_id == file_id)
        .order_by(Flashcard.created_at.desc())
        .limit(DEDUP_FRONT_CAP)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Card validation
# ---------------------------------------------------------------------------

def _validate_cards(raw: list) -> list[dict]:
    valid = []
    for card in raw:
        if not isinstance(card, dict):
            continue
        front = card.get("front", "")
        back = card.get("back", "")
        ctype = card.get("type", "")
        if (
            isinstance(front, str) and front.strip() and len(front) <= 300
            and isinstance(back, str) and back.strip() and len(back) <= 1000
            and ctype in _VALID_TYPES
        ):
            valid.append({"front": front.strip(), "back": back.strip(), "type": ctype})
    return valid


# ---------------------------------------------------------------------------
# LLM call + generation
# ---------------------------------------------------------------------------

async def _call_generate_llm(
    context: str,
    n: int,
    file_url: str,
    existing_fronts: list[str],
    temperature: float = 0.7,
) -> list[dict]:
    dedup_block = ""
    if existing_fronts:
        listed = "\n".join(f'  - "{f}"' for f in existing_fronts[:50])
        dedup_block = (
            "\nDO NOT generate cards whose front is semantically similar to any of "
            "these already-existing cards for this user:\n"
            f"{listed}\n"
        )

    system_prompt = (
        f"You create educational flashcards GROUNDED ONLY in the provided context.\n"
        f"Output STRICT JSON only: {{\"cards\": [...]}}, EXACTLY {n} entries.\n"
        "Each entry:\n"
        '  {"front": "...", "back": "...", "type": "definition"|"concept"|"example"|"formula"}\n'
        "Rules:\n"
        "- front: concise term, question, or scenario (max 20 words)\n"
        "- back: clear answer or explanation, 1-4 sentences, no bullet lists\n"
        "- type mix: ~50% definition, ~25% concept, ~25% example; "
        "use formula when content warrants it\n"
        "- Cover the document uniformly — do not focus on any single topic\n"
        "- Never invent facts not supported by the context\n"
        f"{dedup_block}"
        "Output JSON only — no markdown fences."
    )
    user_prompt = (
        f"File: {file_url}\n"
        f"N: {n}\n"
        f"CONTEXT:\n{context}"
    )
    raw = await openai_llm_func(user_prompt, system_prompt=system_prompt, temperature=temperature)

    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]

    parsed = parse_json_robust(text)
    if not parsed:
        return []
    cards = parsed.get("cards", [])
    return cards if isinstance(cards, list) else []


async def generate_cards(
    context: str,
    n: int,
    file_url: str,
    existing_fronts: list[str],
) -> list[dict]:
    """Call LLM to produce N cards; retry on shortfall."""
    cards = await _call_generate_llm(context, n, file_url, existing_fronts)
    valid = _validate_cards(cards)

    if len(valid) < n:
        missing = n - len(valid)
        logger.info("generate_cards: retrying to fill %d missing cards", missing)
        try:
            extra = await _call_generate_llm(
                context, missing, file_url, existing_fronts, temperature=0.0
            )
            valid += _validate_cards(extra)
        except Exception:
            logger.warning("generate_cards: retry failed", exc_info=True)

    if len(valid) < n:
        raise MalformedCardsError(
            f"LLM produced only {len(valid)} valid cards; expected {n}."
        )
    return valid[:n]


# ---------------------------------------------------------------------------
# Leitner box review
# ---------------------------------------------------------------------------

def review_card(box: int, result: str) -> tuple[int, datetime]:
    """Pure function: advance or regress box, return new_box and next_review_at."""
    if result == "know":
        new_box = min(box + 1, 5)
    elif result == "unsure":
        new_box = max(box - 1, 1)
    else:  # "forgot"
        new_box = 1
    days = LEITNER_INTERVALS[new_box]
    next_review = datetime.utcnow() + timedelta(days=days)
    return new_box, next_review


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def generate_deck_task(deck_id: int) -> None:
    """Background task: generate flashcards and persist to FlashcardDeck."""
    from app.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        deck: FlashcardDeck | None = await db.get(FlashcardDeck, deck_id)
        if deck is None:
            logger.error("generate_deck_task: deck_id=%s not found", deck_id)
            return

        file, classroom = await _resolve_file_classroom(db, deck.file_id)

        try:
            deck.status = FlashcardDeckStatus.GENERATING
            await db.commit()

            from app.services.classroom_rag import classroom_rag_service
            engine = await classroom_rag_service.get_engine(classroom.id)

            ctx, ctx_meta = await build_deck_context(engine, file.file_url)

            existing_fronts = await _collect_existing_fronts(db, deck.user_id, deck.file_id)
            dedup_skipped_estimate = len(existing_fronts)

            t0 = time.time()
            cards = await generate_cards(ctx, deck.card_count, file.file_url, existing_fronts)

            now = datetime.utcnow()
            card_rows = [
                Flashcard(
                    deck_id=deck.id,
                    file_id=deck.file_id,
                    user_id=deck.user_id,
                    front=c["front"],
                    back=c["back"],
                    card_type=FlashcardCardType(c["type"]),
                    box=1,
                    next_review_at=now,
                )
                for c in cards
            ]
            db.add_all(card_rows)

            deck.card_count = len(cards)
            deck.generation_meta = {
                **ctx_meta,
                "elapsed_s": round(time.time() - t0, 2),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "dedup_skipped": dedup_skipped_estimate,
            }
            deck.status = FlashcardDeckStatus.READY
            deck.ready_at = datetime.utcnow()
            await db.commit()
            logger.info(
                "generate_deck_task: deck_id=%s ready (%d cards)", deck_id, len(cards)
            )

        except Exception as exc:
            logger.exception("generate_deck_task failed for deck_id=%s", deck_id)
            deck.status = FlashcardDeckStatus.FAILED
            deck.error_msg = str(exc)[:500]
            await db.commit()
