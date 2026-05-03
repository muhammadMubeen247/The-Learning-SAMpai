"""Add mindmap and mindmap_node_chats tables

Revision ID: b2c3d4e5f6a7
Revises: a6b7c8d9e0f1
Create Date: 2026-05-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types (safe to call if they already exist — init_db may have
    # created them via create_all()).
    mindmapstatus = postgresql.ENUM(
        "pending", "generating", "ready", "failed",
        name="mindmapstatus",
        create_type=False,
    )
    mindmapstatus.create(op.get_bind(), checkfirst=True)

    mindmapmessagerole = postgresql.ENUM(
        "user", "assistant", "marker",
        name="mindmapmessagerole",
        create_type=False,
    )
    mindmapmessagerole.create(op.get_bind(), checkfirst=True)

    # mindmaps table
    op.execute("""
        CREATE TABLE IF NOT EXISTS mindmaps (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
            root_topic VARCHAR(120),
            root_description TEXT,
            tree_data JSONB NOT NULL DEFAULT '{}',
            status mindmapstatus NOT NULL DEFAULT 'pending',
            error_message VARCHAR(500),
            node_count INTEGER NOT NULL DEFAULT 0,
            generation_meta JSONB DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mindmaps_file_id UNIQUE (file_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mindmap_classroom_status
        ON mindmaps (classroom_id, status)
    """)

    # mindmap_node_chats table
    op.execute("""
        CREATE TABLE IF NOT EXISTS mindmap_node_chats (
            id SERIAL PRIMARY KEY,
            mindmap_id INTEGER NOT NULL REFERENCES mindmaps(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            node_id VARCHAR(64),
            role mindmapmessagerole NOT NULL,
            content TEXT NOT NULL,
            message_metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mindmap_chat_user_time
        ON mindmap_node_chats (mindmap_id, user_id, created_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mindmap_chat_node
        ON mindmap_node_chats (mindmap_id, user_id, node_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mindmap_node_chats")
    op.execute("DROP TABLE IF EXISTS mindmaps")
    op.execute("DROP TYPE IF EXISTS mindmapmessagerole")
    op.execute("DROP TYPE IF EXISTS mindmapstatus")
