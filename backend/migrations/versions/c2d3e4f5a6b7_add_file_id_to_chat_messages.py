"""Add file_id column to chat_messages

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-24 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete existing chat_messages rows that predate the file_id column —
    # they have no valid file association and cannot be migrated.
    op.execute("DELETE FROM chat_messages")

    op.add_column(
        "chat_messages",
        sa.Column("file_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_chat_messages_file_id",
        "chat_messages",
        "files",
        ["file_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_chat_messages_file_id", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "file_id")
