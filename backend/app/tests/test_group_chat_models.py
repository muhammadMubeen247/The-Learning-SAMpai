"""Phase 1 tests — group chat schema + SAMpai system user + signup guard.

Unit tests run without a real DB (import-level only).
Integration tests need Postgres running — marked with @pytest.mark.integration.
"""
import os
import pytest


# ── Unit tests — no DB needed ─────────────────────────────────────────────────

def test_models_importable():
    from app.models.group_chat import (
        GroupChat,
        GroupChatMember,
        GroupChatInvite,
        GroupChatMessage,
        GroupRole,
        InviteStatus,
        GroupMessageRole,
    )
    assert GroupRole.OWNER.value == "owner"
    assert InviteStatus.PENDING.value == "pending"
    assert GroupMessageRole.AGENT.value == "agent"


def test_user_has_is_system():
    from app.models.user import User
    col = User.__table__.columns["is_system"]
    assert not col.nullable
    assert col.default.arg is False


def test_reserved_username_check():
    """The RESERVED_USERNAMES constant must include 'sampai' (case-folded)."""
    from app.constants import RESERVED_USERNAMES
    assert "sampai" in RESERVED_USERNAMES


# ── Integration tests — need real Postgres ────────────────────────────────────

@pytest.fixture
def db_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration test")
    return url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sampai_user_exists(db_url):
    from sqlalchemy import select
    from app.database.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.username == "SAMpai", User.is_system.is_(True))
        )
        user = result.scalar_one_or_none()

    assert user is not None, "SAMpai system user not found — run alembic upgrade head"
    assert user.hashed_password == "!locked!"
    assert user.is_system is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_chat_tables_exist(db_url):
    """Trivial insert/select on each new table."""
    from datetime import datetime
    from sqlalchemy import select
    from app.database.session import AsyncSessionLocal
    from app.models.user import User
    from app.models.classroom import Classroom
    from app.models.folder import Folder
    from app.models.file import File, ProcessingStatus
    from app.models.group_chat import (
        GroupChat, GroupChatMember, GroupChatInvite, GroupChatMessage,
        GroupRole, InviteStatus, GroupMessageRole,
    )
    import uuid

    async with AsyncSessionLocal() as db:
        # Fetch the SAMpai user (seeded by migration)
        result = await db.execute(select(User).where(User.username == "SAMpai"))
        sampai = result.scalar_one()

        # Fetch the first classroom + file we can find, or skip if DB is empty
        cl_result = await db.execute(select(Classroom).limit(1))
        classroom = cl_result.scalar_one_or_none()
        if classroom is None:
            pytest.skip("No classroom in DB — populate DB before running this test")

        file_result = await db.execute(select(File).limit(1))
        file_obj = file_result.scalar_one_or_none()
        if file_obj is None:
            pytest.skip("No file in DB — populate DB before running this test")

        # Create a group chat
        gc = GroupChat(
            file_id=file_obj.id,
            classroom_id=classroom.id,
            created_by=sampai.id,
            name="test group",
        )
        db.add(gc)
        await db.flush()

        # Member
        member = GroupChatMember(
            group_chat_id=gc.id,
            user_id=sampai.id,
            role=GroupRole.OWNER,
        )
        db.add(member)
        await db.flush()

        # Message
        msg = GroupChatMessage(
            group_chat_id=gc.id,
            seq=1,
            user_id=sampai.id,
            role=GroupMessageRole.SYSTEM,
            content="test content",
            client_msg_id=uuid.uuid4(),
        )
        db.add(msg)
        await db.flush()

        # Verify we can select them back
        gc_result = await db.execute(select(GroupChat).where(GroupChat.id == gc.id))
        assert gc_result.scalar_one().name == "test group"

        msg_result = await db.execute(
            select(GroupChatMessage).where(GroupChatMessage.group_chat_id == gc.id)
        )
        assert msg_result.scalar_one().seq == 1

        # Rollback — don't pollute DB with test data
        await db.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signup_blocks_reserved_usernames(db_url):
    """HTTP-level test: SAMpai / sampai / SAMPAI all return 422."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for username in ["SAMpai", "sampai", "SAMPAI"]:
            resp = await client.post("/auth/signup", json={
                "username": username,
                "email": f"{username}@test.local",
                "password": "TestPass123!",
            })
            assert resp.status_code == 422, (
                f"Expected 422 for reserved username '{username}', got {resp.status_code}"
            )
            assert "reserved" in resp.json()["detail"].lower()
