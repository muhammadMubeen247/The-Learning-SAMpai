"""Add naive_ready value to processingstatus enum

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-05-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD VALUE is not transactional in Postgres — must run outside a transaction block.
    # IF NOT EXISTS guard makes the migration idempotent (safe to re-run).
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'naive_ready'")


def downgrade() -> None:
    # Postgres does not support removing enum values; downgrade is a no-op.
    # To fully revert: recreate the enum without 'naive_ready' and ALTER the column.
    pass
