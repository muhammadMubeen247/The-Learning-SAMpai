"""Add group_chats, group_chat_members, group_chat_invites, group_chat_messages and is_system flag

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-05-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_system to users
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE
    """)

    # Enum types — idempotent
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE grouprole AS ENUM ('owner', 'member');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE invitestatus AS ENUM ('pending', 'accepted', 'rejected', 'expired', 'cancelled');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE groupmessagerole AS ENUM ('user', 'agent', 'system');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$
    """)

    # group_chats
    op.execute("""
        CREATE TABLE IF NOT EXISTS group_chats (
            id           SERIAL PRIMARY KEY,
            file_id      INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
            created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
            name         VARCHAR(120),
            is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gc_file_archived ON group_chats (file_id, is_archived)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gc_classroom ON group_chats (classroom_id)"
    )

    # group_chat_members (composite PK)
    op.execute("""
        CREATE TABLE IF NOT EXISTS group_chat_members (
            group_chat_id INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role          grouprole NOT NULL,
            joined_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            last_read_seq BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (group_chat_id, user_id)
        )
    """)

    # group_chat_invites
    op.execute("""
        CREATE TABLE IF NOT EXISTS group_chat_invites (
            id            SERIAL PRIMARY KEY,
            group_chat_id INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
            inviter_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invitee_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status        invitestatus NOT NULL DEFAULT 'pending',
            created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            responded_at  TIMESTAMP
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_gc_invite_per_invitee
        ON group_chat_invites (group_chat_id, invitee_id)
    """)

    # group_chat_messages
    op.execute("""
        CREATE TABLE IF NOT EXISTS group_chat_messages (
            id             SERIAL PRIMARY KEY,
            group_chat_id  INTEGER NOT NULL REFERENCES group_chats(id) ON DELETE CASCADE,
            seq            BIGINT NOT NULL,
            user_id        INTEGER REFERENCES users(id) ON DELETE SET NULL,
            role           groupmessagerole NOT NULL,
            content        TEXT NOT NULL,
            mentions       JSONB NOT NULL DEFAULT '[]',
            reply_to_id    INTEGER REFERENCES group_chat_messages(id) ON DELETE SET NULL,
            is_discarded   BOOLEAN NOT NULL DEFAULT FALSE,
            discard_reason VARCHAR(255),
            client_msg_id  UUID,
            created_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_gc_message_seq
        ON group_chat_messages (group_chat_id, seq)
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gcm_group_created ON group_chat_messages (group_chat_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gcm_group_user ON group_chat_messages (group_chat_id, user_id)"
    )

    # Seed SAMpai system user
    op.execute("""
        INSERT INTO users (username, email, hashed_password, is_system)
        VALUES ('SAMpai', 'sampai@system.local', '!locked!', TRUE)
        ON CONFLICT (username) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE username = 'SAMpai' AND is_system = TRUE")
    op.execute("DROP TABLE IF EXISTS group_chat_messages")
    op.execute("DROP TABLE IF EXISTS group_chat_invites")
    op.execute("DROP TABLE IF EXISTS group_chat_members")
    op.execute("DROP TABLE IF EXISTS group_chats")
    op.execute("DROP TYPE IF EXISTS groupmessagerole")
    op.execute("DROP TYPE IF EXISTS invitestatus")
    op.execute("DROP TYPE IF EXISTS grouprole")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_system")
