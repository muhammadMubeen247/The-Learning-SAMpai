"""Add flashcard_decks, flashcards, and flashcard_reviews tables

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum types — DO..EXCEPTION is idempotent when create_all() has already run.
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE flashcarddeckstatus AS ENUM ('pending', 'generating', 'ready', 'failed');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE flashcardcardtype AS ENUM ('definition', 'concept', 'example', 'formula');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # Tables — use IF NOT EXISTS so this is safe even when create_all() ran first.
    op.execute("""
        CREATE TABLE IF NOT EXISTS flashcard_decks (
            id          SERIAL PRIMARY KEY,
            file_id     INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status      flashcarddeckstatus NOT NULL DEFAULT 'pending',
            card_count  INTEGER,
            generation_meta JSONB,
            error_msg   TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            ready_at    TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_user_file ON flashcard_decks (user_id, file_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_status ON flashcard_decks (status)"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_deck_per_user_file
        ON flashcard_decks (user_id, file_id)
        WHERE status IN (
            'pending'::flashcarddeckstatus,
            'generating'::flashcarddeckstatus
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id             SERIAL PRIMARY KEY,
            deck_id        INTEGER NOT NULL REFERENCES flashcard_decks(id) ON DELETE CASCADE,
            file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            front          TEXT NOT NULL,
            back           TEXT NOT NULL,
            card_type      flashcardcardtype NOT NULL,
            box            INTEGER NOT NULL DEFAULT 1,
            next_review_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_card_user_file ON flashcards (user_id, file_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_card_due ON flashcards (user_id, next_review_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS flashcard_reviews (
            id          SERIAL PRIMARY KEY,
            card_id     INTEGER NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            result      VARCHAR(10) NOT NULL,
            box_before  INTEGER NOT NULL,
            box_after   INTEGER NOT NULL,
            reviewed_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_card_user ON flashcard_reviews (card_id, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS flashcard_reviews")
    op.execute("DROP TABLE IF EXISTS flashcards")
    op.execute("DROP TABLE IF EXISTS flashcard_decks")
    op.execute("DROP TYPE IF EXISTS flashcardcardtype")
    op.execute("DROP TYPE IF EXISTS flashcarddeckstatus")
