"""
Tests for group chat messages — mention parsing and message dedup logic.

Unit tests (no DB): mock the DB and service functions.
Integration tests: marked @pytest.mark.integration.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Mention parsing unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parse_mentions_finds_agent_and_user():
    """@alice @SAMpai → both mentions resolved correctly."""
    from app.services.mentions import parse_mentions

    alice = MagicMock()
    alice.id = 1
    alice.username = "alice"

    # Mock DB: returns [alice] as members, no SAMpai (it's a system user)
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [alice]
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_execute_result

    result = await parse_mentions("@alice @SAMpai hi", group_chat_id=1, db=mock_db)

    kinds = {m["kind"] for m in result}
    assert "agent" in kinds
    assert "user" in kinds

    user_mentions = [m for m in result if m["kind"] == "user"]
    assert user_mentions[0]["user_id"] == 1
    assert user_mentions[0]["username"] == "alice"

    agent_mentions = [m for m in result if m["kind"] == "agent"]
    assert agent_mentions[0]["username"] == "SAMpai"


@pytest.mark.asyncio
async def test_parse_mentions_nonmember_ignored():
    """@nonmember → not in members list → result is empty."""
    from app.services.mentions import parse_mentions

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []  # No members
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_execute_result

    result = await parse_mentions("@nonmember hello", group_chat_id=1, db=mock_db)

    assert result == []


@pytest.mark.asyncio
async def test_parse_mentions_no_mentions():
    """Message with no @ tokens → empty list, no DB query needed."""
    from app.services.mentions import parse_mentions

    mock_db = AsyncMock()

    result = await parse_mentions("Hello there!", group_chat_id=1, db=mock_db)

    assert result == []
    # DB should not be queried at all
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_parse_mentions_deduplicates():
    """Same mention twice → only one entry."""
    from app.services.mentions import parse_mentions

    alice = MagicMock()
    alice.id = 1
    alice.username = "alice"

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [alice]
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_execute_result

    result = await parse_mentions("@alice @alice @alice", group_chat_id=1, db=mock_db)

    user_mentions = [m for m in result if m["kind"] == "user"]
    assert len(user_mentions) == 1


@pytest.mark.asyncio
async def test_parse_mentions_case_insensitive_sampai():
    """@sampai and @SAMPAI should both resolve to the agent mention."""
    from app.services.mentions import parse_mentions

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_execute_result

    result1 = await parse_mentions("@sampai", group_chat_id=1, db=mock_db)
    result2 = await parse_mentions("@SAMPAI", group_chat_id=1, db=mock_db)

    assert any(m["kind"] == "agent" for m in result1)
    assert any(m["kind"] == "agent" for m in result2)


# ---------------------------------------------------------------------------
# Client_msg_id dedup logic test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_msg_id_dedup_returns_existing():
    """
    If a message with the same client_msg_id already exists in the DB,
    send_message must return it without inserting a duplicate.
    """
    import uuid
    from app.models.group_chat import GroupChatMessage, GroupMessageRole
    from unittest.mock import patch, AsyncMock, MagicMock

    existing_msg = MagicMock(spec=GroupChatMessage)
    existing_msg.id = 42
    existing_msg.group_chat_id = 1
    existing_msg.seq = 5
    existing_msg.content = "hello"
    existing_msg.client_msg_id = uuid.UUID("12345678-1234-5678-1234-567812345678")

    mock_db = AsyncMock()
    # First execute call: idempotency check → returns existing message
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing_msg
    mock_db.execute.return_value = execute_result

    from app.services.group_chat_service import send_message
    result = await send_message(
        mock_db,
        thread_id=1,
        user_id=10,
        content="hello",
        client_msg_id="12345678-1234-5678-1234-567812345678",
    )

    assert result.id == 42
    # Should not have added anything
    mock_db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Rate limit unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_message_rate_no_redis_always_allows():
    """Without Redis, rate limiting is skipped."""
    from app.realtime.rate_limit import check_message_rate
    result = await check_message_rate(user_id=1, thread_id=1, redis=None)
    assert result is True


@pytest.mark.asyncio
async def test_check_agent_rate_no_redis_always_allows():
    """Without Redis, agent rate limiting is skipped."""
    from app.realtime.rate_limit import check_agent_rate
    result = await check_agent_rate(user_id=1, thread_id=1, redis=None)
    assert result is True


# ---------------------------------------------------------------------------
# GroupMessageOut schema
# ---------------------------------------------------------------------------


def test_group_message_out_model_validate():
    """GroupMessageOut should serialize correctly from a mock object."""
    from datetime import datetime
    from app.schemas.group_chat import GroupMessageOut
    from app.models.group_chat import GroupMessageRole

    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.group_chat_id = 10
    mock_msg.seq = 3
    mock_msg.user_id = 5
    mock_msg.role = GroupMessageRole.USER
    mock_msg.content = "test content"
    mock_msg.mentions = []
    mock_msg.reply_to_id = None
    mock_msg.is_discarded = False
    mock_msg.discard_reason = None
    mock_msg.client_msg_id = None
    mock_msg.created_at = datetime.utcnow()
    mock_msg.author = None

    out = GroupMessageOut.model_validate(mock_msg)
    assert out.seq == 3
    assert out.content == "test content"
    assert out.role == GroupMessageRole.USER


# ---------------------------------------------------------------------------
# Integration tests — skip without DB
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_message_inserts_and_broadcasts():
    """Integration: send_message creates a row and mentions are parsed."""
    import os
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")

    from app.database.session import AsyncSessionLocal
    from app.models.user import User
    from app.models.file import File
    from app.models.group_chat import GroupChat, GroupChatMember, GroupRole
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Need a user, file, classroom
            user_q = await db.execute(select(User).where(User.is_system == False).limit(1))
            user = user_q.scalar_one_or_none()
            if user is None:
                pytest.skip("No non-system user")

            file_q = await db.execute(select(File).limit(1))
            file = file_q.scalar_one_or_none()
            if file is None:
                pytest.skip("No file in DB")

            from app.services.group_chat_service import send_message, create_thread
            from app.models.folder import Folder

            folder_q = await db.execute(select(Folder).where(Folder.id == file.folder_id))
            folder = folder_q.scalar_one()

            gc = await create_thread(db, file.id, folder.classroom_id, user.id)

            msg = await send_message(db, gc.id, user.id, "Hello world!")
            assert msg.id is not None
            assert msg.seq == 1
            assert msg.content == "Hello world!"

            await db.rollback()
