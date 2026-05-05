"""
Flashcard routes — generate deck, poll, review cards, and history.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.file import ProcessingStatus
from app.models.flashcard import (
    Flashcard,
    FlashcardDeck,
    FlashcardDeckStatus,
    FlashcardReview,
)
from app.routes.chat import _get_file_and_classroom
from app.schemas.flashcard import (
    CardPublic,
    DeckDetail,
    DeckHistoryItem,
    DeckHistoryResponse,
    DueCardsResponse,
    GenerateDeckRequest,
    GenerateDeckResponse,
    ReviewRequest,
    ReviewResponse,
)
from app.services import flashcard_service

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])
logger = logging.getLogger(__name__)

_OPEN_STATUSES = (FlashcardDeckStatus.PENDING, FlashcardDeckStatus.GENERATING)
_STALE_GENERATING_MINUTES = 5


def _card_to_public(card: Flashcard) -> CardPublic:
    return CardPublic(
        id=card.id,
        front=card.front,
        back=card.back,
        card_type=card.card_type.value,
        box=card.box,
        next_review_at=card.next_review_at,
    )


# ---------------------------------------------------------------------------
# POST /flashcards/files/{file_id}/generate
# ---------------------------------------------------------------------------

@router.post("/files/{file_id}/generate", response_model=GenerateDeckResponse, status_code=202)
async def generate_deck(
    file_id: int,
    body: GenerateDeckRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    file, classroom = await _get_file_and_classroom(file_id, current_user, db)

    if file.processing_status not in (ProcessingStatus.NAIVE_READY, ProcessingStatus.COMPLETED):
        raise HTTPException(
            status_code=400,
            detail="File is still being processed. Please wait a moment.",
        )

    result = await db.execute(
        select(FlashcardDeck)
        .where(
            FlashcardDeck.user_id == current_user.id,
            FlashcardDeck.file_id == file_id,
            FlashcardDeck.status.in_(_OPEN_STATUSES),
        )
        .order_by(FlashcardDeck.created_at.desc())
    )
    open_deck: FlashcardDeck | None = result.scalars().first()

    if open_deck is not None:
        stale_cutoff = datetime.utcnow() - timedelta(minutes=_STALE_GENERATING_MINUTES)
        if (
            open_deck.status == FlashcardDeckStatus.GENERATING
            and open_deck.created_at < stale_cutoff
        ):
            open_deck.status = FlashcardDeckStatus.FAILED
            open_deck.error_msg = "abandoned — timed out during generation"
            await db.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail="Flashcard deck generation is already in progress for this file.",
            )

    new_deck = FlashcardDeck(
        file_id=file_id,
        user_id=current_user.id,
        status=FlashcardDeckStatus.PENDING,
        card_count=body.card_count,
    )
    db.add(new_deck)
    try:
        await db.commit()
        await db.refresh(new_deck)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Flashcard deck generation is already in progress for this file.",
        )

    background_tasks.add_task(flashcard_service.generate_deck_task, new_deck.id)
    logger.info(
        "generate_deck: queued deck_id=%s file_id=%s user_id=%s card_count=%s",
        new_deck.id, file_id, current_user.id, body.card_count,
    )
    return GenerateDeckResponse(deck_id=new_deck.id, status="pending")


# ---------------------------------------------------------------------------
# GET /flashcards/files/{file_id}/due
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}/due", response_model=DueCardsResponse)
async def get_due_cards(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_file_and_classroom(file_id, current_user, db)

    result = await db.execute(
        select(Flashcard)
        .where(
            Flashcard.user_id == current_user.id,
            Flashcard.file_id == file_id,
            Flashcard.next_review_at <= datetime.utcnow(),
        )
        .order_by(Flashcard.next_review_at)
    )
    cards = result.scalars().all()
    return DueCardsResponse(
        cards=[_card_to_public(c) for c in cards],
        total_due=len(cards),
    )


# ---------------------------------------------------------------------------
# GET /flashcards/files/{file_id}/history
# ---------------------------------------------------------------------------

@router.get("/files/{file_id}/history", response_model=DeckHistoryResponse)
async def get_deck_history(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await _get_file_and_classroom(file_id, current_user, db)

    result = await db.execute(
        select(FlashcardDeck)
        .where(
            FlashcardDeck.file_id == file_id,
            FlashcardDeck.user_id == current_user.id,
        )
        .order_by(FlashcardDeck.created_at.desc())
    )
    decks = result.scalars().all()

    items = []
    has_open = False
    open_deck_id: int | None = None

    for d in decks:
        items.append(
            DeckHistoryItem(
                deck_id=d.id,
                status=d.status.value,
                card_count=d.card_count,
                created_at=d.created_at,
                ready_at=d.ready_at,
            )
        )
        if d.status in _OPEN_STATUSES and not has_open:
            has_open = True
            open_deck_id = d.id

    # Box counts for the latest ready deck
    box_counts: dict[str, int] | None = None
    latest_ready = next((d for d in decks if d.status == FlashcardDeckStatus.READY), None)
    if latest_ready is not None:
        agg_result = await db.execute(
            select(Flashcard.box, func.count(Flashcard.id).label("cnt"))
            .where(Flashcard.deck_id == latest_ready.id)
            .group_by(Flashcard.box)
        )
        box_counts = {str(row.box): row.cnt for row in agg_result}

    return DeckHistoryResponse(
        items=items,
        box_counts=box_counts,
        has_open_deck=has_open,
        open_deck_id=open_deck_id,
    )


# ---------------------------------------------------------------------------
# GET /flashcards/{deck_id}
# ---------------------------------------------------------------------------

@router.get("/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _res = await db.execute(
        select(FlashcardDeck)
        .options(selectinload(FlashcardDeck.cards))
        .where(FlashcardDeck.id == deck_id)
    )
    deck: FlashcardDeck | None = _res.scalar_one_or_none()
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    await _get_file_and_classroom(deck.file_id, current_user, db)

    cards_public = [_card_to_public(c) for c in deck.cards] if deck.status == FlashcardDeckStatus.READY else None

    return DeckDetail(
        deck_id=deck.id,
        status=deck.status.value,
        card_count=deck.card_count,
        created_at=deck.created_at,
        ready_at=deck.ready_at,
        error_msg=deck.error_msg,
        cards=cards_public,
    )


# ---------------------------------------------------------------------------
# POST /flashcards/cards/{card_id}/review
# ---------------------------------------------------------------------------

@router.post("/cards/{card_id}/review", response_model=ReviewResponse)
async def review_card(
    card_id: int,
    body: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    card: Flashcard | None = await db.get(Flashcard, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    box_before = card.box
    new_box, next_review_at = flashcard_service.review_card(card.box, body.result)

    card.box = new_box
    card.next_review_at = next_review_at

    review_row = FlashcardReview(
        card_id=card.id,
        user_id=current_user.id,
        result=body.result,
        box_before=box_before,
        box_after=new_box,
    )
    db.add(review_row)
    await db.commit()

    return ReviewResponse(
        card_id=card.id,
        box=new_box,
        next_review_at=next_review_at,
    )
