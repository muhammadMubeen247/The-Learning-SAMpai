from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

CardType = Literal["definition", "concept", "example", "formula"]
DeckStatus = Literal["pending", "generating", "ready", "failed"]
ReviewResult = Literal["know", "unsure", "forgot"]


class GenerateDeckRequest(BaseModel):
    card_count: Literal[10, 20, 30] = 20


class GenerateDeckResponse(BaseModel):
    deck_id: int
    status: DeckStatus


class CardPublic(BaseModel):
    id: int
    front: str
    back: str
    card_type: CardType
    box: int
    next_review_at: datetime


class DeckDetail(BaseModel):
    deck_id: int
    status: DeckStatus
    card_count: Optional[int] = None
    created_at: datetime
    ready_at: Optional[datetime] = None
    error_msg: Optional[str] = None
    cards: Optional[list[CardPublic]] = None


class DueCardsResponse(BaseModel):
    cards: list[CardPublic]
    total_due: int


class ReviewRequest(BaseModel):
    result: ReviewResult


class ReviewResponse(BaseModel):
    card_id: int
    box: int
    next_review_at: datetime


class DeckHistoryItem(BaseModel):
    deck_id: int
    status: DeckStatus
    card_count: Optional[int] = None
    created_at: datetime
    ready_at: Optional[datetime] = None


class DeckHistoryResponse(BaseModel):
    items: list[DeckHistoryItem]
    box_counts: Optional[dict[str, int]] = None
    has_open_deck: bool
    open_deck_id: Optional[int] = None
