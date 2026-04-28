"""
Quiz service — background quiz generation, difficulty inference, grading.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import Quiz, QuizAttempt, QuizDifficulty, QuizStatus
from app.rag.base import QueryParam
from app.rag.utils import parse_json_robust, openai_llm_func
from app.services.chat_service import get_conversation_history_for_rag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Difficulty → retrieval parameters
# ---------------------------------------------------------------------------

DIFF_PARAMS: dict[QuizDifficulty, dict[str, int]] = {
    QuizDifficulty.EASY:   dict(traversal_hops=1, max_graph_neighbors=10, top_k=15, chunk_top_k=8),
    QuizDifficulty.MEDIUM: dict(traversal_hops=2, max_graph_neighbors=20, top_k=25, chunk_top_k=12),
    QuizDifficulty.HARD:   dict(traversal_hops=3, max_graph_neighbors=40, top_k=40, chunk_top_k=20),
}

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class EmptyContextError(Exception):
    pass


class MalformedQuestionsError(Exception):
    pass


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

async def infer_difficulty(
    db: AsyncSession,
    file_id: int,
    user_id: int,
) -> tuple[QuizDifficulty, str]:
    """Infer quiz difficulty from chat history + past attempts.

    Returns (difficulty, source) where source is "inferred" or "baseline".
    """
    chat_turns = await get_conversation_history_for_rag(db, file_id, user_id, limit=20)
    result = await db.execute(
        select(QuizAttempt)
        .join(Quiz, QuizAttempt.quiz_id == Quiz.id)
        .where(QuizAttempt.user_id == user_id, QuizAttempt.file_id == file_id)
        .order_by(QuizAttempt.submitted_at.desc())
        .limit(3)
    )
    past_attempts = result.scalars().all()

    if not chat_turns and not past_attempts:
        return QuizDifficulty.MEDIUM, "baseline"

    attempts_summary = "\n".join(
        f"- score={a.score:.0%}, correct={a.correct_count}/{a.total_count}"
        for a in past_attempts
    ) or "None"
    chat_summary = "\n".join(
        f"{m['role']}: {m['content'][:120]}" for m in chat_turns[-10:]
    ) or "None"

    system_prompt = (
        "You are a difficulty-calibration agent. Choose the next quiz difficulty "
        "for a learner. Output STRICT JSON only: "
        '{"difficulty": "easy"|"medium"|"hard", "reason": "<short>"}.\n\n'
        "Heuristics:\n"
        "  - past avg score >= 0.8 -> step UP\n"
        "  - past avg score <  0.5 -> step DOWN\n"
        "  - chat shows confusion (\"don't understand\", \"confused\", \"what is X\") "
        "-> step DOWN or stay easy\n"
        "  - chat shows synthesis questions (\"how does A relate to B\", "
        "\"why does X cause Y\") -> stay/go harder\n"
        "  - default uncertain -> medium"
    )
    user_prompt = (
        f"Past attempts (most recent first):\n{attempts_summary}\n\n"
        f"Recent chat snippets:\n{chat_summary}"
    )

    try:
        raw = await openai_llm_func(user_prompt, system_prompt=system_prompt)
        parsed = parse_json_robust(raw)
        if parsed and parsed.get("difficulty") in ("easy", "medium", "hard"):
            return QuizDifficulty(parsed["difficulty"]), "inferred"
    except Exception:
        logger.warning("infer_difficulty LLM call failed; falling back to baseline", exc_info=True)

    return QuizDifficulty.MEDIUM, "baseline"


def _extract_chat_topics(
    chat_turns: list[dict],
    max_topics: int = 8,
    max_chars_per_topic: int = 200,
) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for turn in reversed(chat_turns):  # most recent first
        if turn.get("role") != "user":
            continue
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        snippet = content[:max_chars_per_topic]
        key = snippet.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(snippet)
        if len(topics) >= max_topics:
            break
    return list(reversed(topics))  # restore chronological order


async def build_quiz_context(
    engine: Any,
    file_url: str,
    difficulty: QuizDifficulty,
    chat_topics: list[str] | None = None,
) -> tuple[str, dict]:
    """Retrieve file-scoped context from the RAG engine for question generation."""
    params = DIFF_PARAMS[difficulty]
    qp = QueryParam(
        mode="mix",
        only_need_context=True,
        file_filter=file_url,
        **params,
    )
    if chat_topics:
        joined = " | ".join(chat_topics)
        seed = (
            "Topics the learner has recently been studying and asking about: "
            f"{joined}. Retrieve passages that explain, define, compare, or "
            "give examples of these topics in the document."
        )
        print("Quiz context seed with chat topics:", seed)
    else:
        seed = "Key concepts, definitions, relationships, and examples in this document."
    result = await engine.aquery(seed, qp)
    ctx = (result.content if result else "") or ""
    if not ctx.strip():
        raise EmptyContextError(
            "No content could be retrieved for this file. "
            "The file may not have been fully processed yet."
        )
    return ctx, {"context_chars": len(ctx), "chat_topics_count": len(chat_topics or []), **params}


async def generate_questions(
    context: str,
    difficulty: QuizDifficulty,
    num_questions: int,
    file_url: str,
    chat_topics: list[str] | None = None,
) -> list[dict]:
    """Call the LLM to produce N quiz questions grounded in context."""
    questions = await _call_generate_llm(context, difficulty, num_questions, file_url, chat_topics=chat_topics)
    valid = _validate_questions(questions, num_questions)
    if len(valid) < num_questions:
        # One retry for missing questions
        missing = num_questions - len(valid)
        logger.info("generate_questions: retrying to fill %d missing questions", missing)
        try:
            extra = await _call_generate_llm(context, difficulty, missing, file_url, temperature=0.0, chat_topics=chat_topics)
            valid += _validate_questions(extra, missing)
        except Exception:
            logger.warning("generate_questions: retry failed", exc_info=True)
    if len(valid) < num_questions:
        raise MalformedQuestionsError(
            f"LLM produced only {len(valid)} valid questions; expected {num_questions}."
        )
    # Re-number ids sequentially
    for i, q in enumerate(valid[:num_questions], start=1):
        q["id"] = i
    return valid[:num_questions]


async def _call_generate_llm(
    context: str,
    difficulty: QuizDifficulty,
    n: int,
    file_url: str,
    temperature: float = 0.7,
    chat_topics: list[str] | None = None,
) -> list[dict]:
    focus_block = ""
    if chat_topics:
        bulleted = "\n".join(f"  - {t}" for t in chat_topics)
        focus_block = (
            "\nFOCUS AREAS — the learner has recently been studying these topics "
            "in chat. Weight roughly 60-70% of questions toward these areas; the "
            "remaining questions may cover other key concepts in the context. "
            "Do NOT invent topics not supported by the context.\n"
            f"{bulleted}\n"
        )
    system_prompt = (
        f"You write self-contained quiz questions GROUNDED ONLY in the provided context.\n"
        f"Output STRICT JSON only: {{\"questions\": [...]}}, EXACTLY {n} entries.\n"
        "Each entry one of:\n"
        '  MCQ:  {"id": <1..N>, "type": "mcq", "prompt": "...", '
        '"options": ["A","B","C","D"], "answer": <0..3>, '
        '"explanation": "...", "source_hint": "..."}\n'
        '  T/F:  {"id": <1..N>, "type": "tf", "prompt": "<assertion>", '
        '"answer": true|false, "explanation": "...", "source_hint": "..."}\n'
        f"Difficulty: {difficulty.value}.\n"
        "  - easy:   recall of definitions / direct facts.\n"
        "  - medium: comparisons, application of one concept.\n"
        "  - hard:   synthesis across two concepts, cause-effect, edge cases.\n"
        f"{focus_block}"
        "Mix MCQ and TF ~70/30. Distractors must be plausible but unambiguously wrong "
        "per the context. Never invent facts. No \"according to the document above\" "
        "framing. Output JSON only — no markdown fences."
    )
    user_prompt = (
        f"File: {file_url}\n"
        f"Difficulty: {difficulty.value}\n"
        f"N: {n}\n"
        f"CONTEXT:\n{context}"
    )
    raw = await openai_llm_func(
        user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
    )
    # Strip accidental code fences
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]

    parsed = parse_json_robust(text)
    if not parsed:
        return []
    questions = parsed.get("questions", [])
    if not isinstance(questions, list):
        return []
    return questions


def _validate_questions(raw: list, expected_n: int) -> list[dict]:
    """Return only structurally valid question dicts."""
    valid = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        qtype = q.get("type")
        if qtype == "mcq":
            opts = q.get("options")
            if (
                isinstance(opts, list)
                and len(opts) == 4
                and isinstance(q.get("answer"), int)
                and 0 <= q["answer"] <= 3
                and q.get("prompt")
                and q.get("explanation")
            ):
                valid.append(q)
        elif qtype == "tf":
            if (
                isinstance(q.get("answer"), bool)
                and q.get("prompt")
                and q.get("explanation")
            ):
                valid.append(q)
    return valid


def grade_attempt(
    quiz_questions: list[dict],
    submit_answers: list[dict],
) -> dict:
    """Grade submitted answers against stored questions."""
    q_map = {q["id"]: q for q in quiz_questions}
    a_map = {a["question_id"]: a["answer"] for a in submit_answers}

    answers_full = []
    correct_count = 0

    for q_id, q in q_map.items():
        user_ans = a_map.get(q_id)
        correct_ans = q["answer"]
        qtype = q["type"]

        # Coerce types
        if qtype == "mcq" and user_ans is not None:
            try:
                user_ans = int(user_ans)
            except (TypeError, ValueError):
                user_ans = None
        elif qtype == "tf" and user_ans is not None:
            if isinstance(user_ans, str):
                user_ans = user_ans.lower() in ("true", "1", "yes")
            else:
                user_ans = bool(user_ans)

        is_correct = user_ans is not None and user_ans == correct_ans
        if is_correct:
            correct_count += 1

        answers_full.append({
            "question_id": q_id,
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "correct": is_correct,
        })

    total = len(q_map)
    score = correct_count / total if total else 0.0
    return {
        "score": score,
        "correct_count": correct_count,
        "total_count": total,
        "answers_full": answers_full,
    }


# ---------------------------------------------------------------------------
# Background task orchestrator
# ---------------------------------------------------------------------------

async def generate_quiz_task(quiz_id: int) -> None:
    """Background task: generate questions and persist to the Quiz row."""
    from app.database.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        quiz: Quiz | None = await db.get(Quiz, quiz_id)
        if quiz is None:
            logger.error("generate_quiz_task: quiz_id=%s not found", quiz_id)
            return

        file, classroom = await _resolve_file_classroom(db, quiz.file_id)

        try:
            quiz.status = QuizStatus.GENERATING
            await db.commit()

            from app.services.classroom_rag import classroom_rag_service
            engine = await classroom_rag_service.get_engine(classroom.id)

            try:
                chat_turns = await get_conversation_history_for_rag(db, quiz.file_id, quiz.user_id, limit=20)
                chat_topics = _extract_chat_topics(chat_turns)
            except Exception:
                logger.warning(
                    "generate_quiz_task: failed to load chat history for quiz_id=%s; "
                    "falling back to generic seed", quiz_id, exc_info=True,
                )
                chat_topics = []

            ctx, ctx_meta = await build_quiz_context(engine, file.file_url, quiz.difficulty, chat_topics=chat_topics)
            t0 = time.time()
            questions = await generate_questions(ctx, quiz.difficulty, quiz.num_questions, file.file_url, chat_topics=chat_topics)

            quiz.questions = questions
            quiz.generation_meta = {
                **ctx_meta,
                "elapsed_s": round(time.time() - t0, 2),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            }
            quiz.status = QuizStatus.READY
            quiz.ready_at = datetime.utcnow()
            await db.commit()
            logger.info("generate_quiz_task: quiz_id=%s ready (%d questions)", quiz_id, len(questions))

        except Exception as exc:
            logger.exception("generate_quiz_task failed for quiz_id=%s", quiz_id)
            quiz.status = QuizStatus.FAILED
            quiz.error_msg = str(exc)[:500]
            await db.commit()


async def _resolve_file_classroom(db: AsyncSession, file_id: int):
    """Return (File, Classroom) for a given file_id."""
    from app.models.file import File
    from app.models.folder import Folder
    from app.models.classroom import Classroom

    file_obj = await db.get(File, file_id)
    if file_obj is None:
        raise ValueError(f"File {file_id} not found")
    folder_obj = await db.get(Folder, file_obj.folder_id)
    if folder_obj is None:
        raise ValueError(f"Folder {file_obj.folder_id} not found")
    classroom_obj = await db.get(Classroom, folder_obj.classroom_id)
    if classroom_obj is None:
        raise ValueError(f"Classroom {folder_obj.classroom_id} not found")
    return file_obj, classroom_obj
