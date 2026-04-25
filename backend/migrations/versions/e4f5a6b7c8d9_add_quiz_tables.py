"""Add quiz and quiz_attempts tables

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-25 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types first with checkfirst=True so this migration is
    # idempotent when create_all() has already run (e.g. dev startup).
    quizstatus = sa.Enum(
        "pending", "generating", "ready", "failed", "submitted",
        name="quizstatus",
        create_type=False,   # we manage creation explicitly below
    )
    quizdifficulty = sa.Enum(
        "easy", "medium", "hard",
        name="quizdifficulty",
        create_type=False,
    )
    # create_type=False stops SQLAlchemy auto-creating inside create_table;
    # we do it ourselves here with checkfirst so a pre-existing type is skipped.
    sa.Enum("pending", "generating", "ready", "failed", "submitted",
            name="quizstatus").create(op.get_bind(), checkfirst=True)
    sa.Enum("easy", "medium", "hard",
            name="quizdifficulty").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "file_id",
            sa.Integer,
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            quizstatus,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("difficulty", quizdifficulty, nullable=False),
        sa.Column("difficulty_source", sa.String(20), nullable=False),
        sa.Column(
            "num_questions",
            sa.Integer,
            nullable=False,
        ),
        sa.Column("questions", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generation_meta", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("ready_at", sa.DateTime, nullable=True),
        sa.CheckConstraint("num_questions IN (5, 10, 15)", name="ck_quiz_num_questions"),
    )
    op.create_index("idx_quiz_user_file", "quizzes", ["user_id", "file_id"])
    op.create_index("idx_quiz_status", "quizzes", ["status"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_one_active_quiz_per_user_file
        ON quizzes (user_id, file_id)
        WHERE status IN ('pending', 'generating', 'ready')
        """
    )

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "quiz_id",
            sa.Integer,
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            sa.Integer,
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("correct_count", sa.Integer, nullable=False),
        sa.Column("total_count", sa.Integer, nullable=False),
        sa.Column("answers", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime,
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_attempt_user_file", "quiz_attempts", ["user_id", "file_id"])


def downgrade() -> None:
    op.drop_index("idx_attempt_user_file", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")

    op.execute("DROP INDEX IF EXISTS uq_one_active_quiz_per_user_file")
    op.drop_index("idx_quiz_status", table_name="quizzes")
    op.drop_index("idx_quiz_user_file", table_name="quizzes")
    op.drop_table("quizzes")

    sa.Enum(name="quizdifficulty").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="quizstatus").drop(op.get_bind(), checkfirst=True)
