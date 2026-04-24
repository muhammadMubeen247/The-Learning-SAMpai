"""Drop legacy topic_id column from chat_messages

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK constraint if it exists (name follows Postgres default convention)
    op.execute(
        "ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_topic_id_fkey"
    )
    # Drop the legacy topic_id column left over from the old topic model
    op.execute(
        "ALTER TABLE chat_messages DROP COLUMN IF EXISTS topic_id"
    )


def downgrade() -> None:
    # topic model has been removed — cannot meaningfully restore; add as nullable
    op.add_column(
        "chat_messages",
        sa.Column("topic_id", sa.Integer(), nullable=True),
    )
