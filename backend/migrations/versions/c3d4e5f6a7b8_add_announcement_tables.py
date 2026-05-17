"""Add announcements and announcement_comments tables

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-15 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "classroom_id",
            sa.Integer,
            sa.ForeignKey("classrooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_announcement_classroom_id", "announcements", ["classroom_id"])
    op.create_index("idx_announcement_created_at", "announcements", ["created_at"])

    op.create_table(
        "announcement_comments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "announcement_id",
            sa.Integer,
            sa.ForeignKey("announcements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_comment_announcement_id", "announcement_comments", ["announcement_id"])


def downgrade() -> None:
    op.drop_index("idx_comment_announcement_id", table_name="announcement_comments")
    op.drop_table("announcement_comments")

    op.drop_index("idx_announcement_created_at", table_name="announcements")
    op.drop_index("idx_announcement_classroom_id", table_name="announcements")
    op.drop_table("announcements")
