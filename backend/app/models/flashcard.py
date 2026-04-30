import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base


class FlashcardDeckStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class FlashcardCardType(str, enum.Enum):
    DEFINITION = "definition"
    CONCEPT = "concept"
    EXAMPLE = "example"
    FORMULA = "formula"


class FlashcardDeck(Base):
    __tablename__ = "flashcard_decks"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(
        SQLEnum(FlashcardDeckStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=FlashcardDeckStatus.PENDING,
    )
    card_count = Column(Integer, nullable=True)
    generation_meta = Column(JSONB, nullable=True)
    error_msg = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ready_at = Column(DateTime, nullable=True)

    cards = relationship(
        "Flashcard",
        back_populates="deck",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_deck_user_file", "user_id", "file_id"),
        Index("idx_deck_status", "status"),
    )


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True, index=True)
    deck_id = Column(Integer, ForeignKey("flashcard_decks.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    card_type = Column(
        SQLEnum(FlashcardCardType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    box = Column(Integer, nullable=False, default=1)
    next_review_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    deck = relationship("FlashcardDeck", back_populates="cards")

    __table_args__ = (
        Index("idx_card_user_file", "user_id", "file_id"),
        Index("idx_card_due", "user_id", "next_review_at"),
    )


class FlashcardReview(Base):
    __tablename__ = "flashcard_reviews"

    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    result = Column(String(10), nullable=False)
    box_before = Column(Integer, nullable=False)
    box_after = Column(Integer, nullable=False)
    reviewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_review_card_user", "card_id", "user_id"),
    )
