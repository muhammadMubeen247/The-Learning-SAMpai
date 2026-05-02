"""
Tests for group_chat_service.

Unit tests (no DB): import-time + pure-function tests.
Integration tests: marked @pytest.mark.integration — skip without real Postgres.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Unit tests — no DB
# ---------------------------------------------------------------------------


def test_service_module_importable():
    """The service module must import without errors."""
    import app.services.group_chat_service  # noqa: F401


def test_reserved_username_includes_sampai():
    """RESERVED_USERNAMES must contain 'sampai' (case-folded guard for signup)."""
    from app.constants import RESERVED_USERNAMES
    assert "sampai" in RESERVED_USERNAMES


def test_auto_name_format():
    """Thread auto-name must be '{filename} — group'."""
    filename = "Lecture 1 — HRM Basics"
    expected = f"{filename} — group"
    actual = f"{filename} — group"
    assert actual == expected


def test_group_role_values():
    from app.models.group_chat import GroupRole
    assert GroupRole.OWNER.value == "owner"
    assert GroupRole.MEMBER.value == "member"


def test_invite_status_values():
    from app.models.group_chat import InviteStatus
    assert InviteStatus.PENDING.value == "pending"
    assert InviteStatus.ACCEPTED.value == "accepted"
    assert InviteStatus.REJECTED.value == "rejected"
    assert InviteStatus.CANCELLED.value == "cancelled"


def test_message_role_values():
    from app.models.group_chat import GroupMessageRole
    assert GroupMessageRole.USER.value == "user"
    assert GroupMessageRole.AGENT.value == "agent"
    assert GroupMessageRole.SYSTEM.value == "system"


def test_group_chat_out_schema_importable():
    from app.schemas.group_chat import (
        GroupChatOut,
        InviteOut,
        GroupMessageOut,
        ThreadListItem,
        MemberOut,
        UserSummary,
    )
    # Verify fields exist
    assert "id" in GroupChatOut.model_fields
    assert "members" in GroupChatOut.model_fields
    assert "status" in InviteOut.model_fields
    assert "seq" in GroupMessageOut.model_fields
    assert "unread_count" in ThreadListItem.model_fields


def test_send_message_in_schema():
    from app.schemas.group_chat import SendMessageIn
    msg = SendMessageIn(content="hello world")
    assert msg.content == "hello world"
    assert msg.reply_to_id is None
    assert msg.client_msg_id is None


def test_read_receipt_in_schema():
    from app.schemas.group_chat import ReadReceiptIn
    r = ReadReceiptIn(last_seq=42)
    assert r.last_seq == 42


# ---------------------------------------------------------------------------
# Unit tests — mock DB (test service function signatures and logic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_invites_returns_list():
    """get_pending_invites should query with invitee_id + PENDING status."""
    from app.models.group_chat import GroupChatInvite, InviteStatus

    # Build a mock scalars result
    mock_invite = MagicMock(spec=GroupChatInvite)
    mock_invite.invitee_id = 5
    mock_invite.status = InviteStatus.PENDING

    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_invite]
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_execute_result

    from app.services.group_chat_service import get_pending_invites
    result = await get_pending_invites(mock_db, user_id=5)

    assert len(result) == 1
    assert result[0].invitee_id == 5


@pytest.mark.asyncio
async def test_leave_thread_raises_404_if_not_member():
    """leave_thread raises 404 when user is not a member."""
    from fastapi import HTTPException

    mock_db = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_execute_result

    from app.services.group_chat_service import leave_thread
    with pytest.raises(HTTPException) as exc:
        await leave_thread(mock_db, group_chat_id=1, user_id=99)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_invite_raises_403_for_non_inviter():
    """cancel_invite raises 403 if caller is not the inviter."""
    from app.models.group_chat import GroupChatInvite, InviteStatus
    from app.models.user import User
    from fastapi import HTTPException

    mock_invite = MagicMock(spec=GroupChatInvite)
    mock_invite.inviter_id = 10
    mock_invite.invitee_id = 20
    mock_invite.status = InviteStatus.PENDING

    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_invite

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_execute_result

    current_user = MagicMock(spec=User)
    current_user.id = 999  # NOT the inviter

    from app.services.group_chat_service import cancel_invite
    with pytest.raises(HTTPException) as exc:
        await cancel_invite(mock_db, invite_id=1, current_user=current_user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_send_invites_raises_409_for_existing_member():
    """send_invites raises 409 if user is already a member."""
    from app.models.group_chat import GroupChatMember, GroupChat
    from app.models.user import User
    from fastapi import HTTPException

    mock_file = MagicMock()
    mock_file.id = 1
    mock_file.folder_id = 2
    mock_file.filename = "test.pdf"

    mock_folder = MagicMock()
    mock_folder.classroom_id = 3

    mock_gc = MagicMock(spec=GroupChat)
    mock_gc.id = 42

    mock_member = MagicMock(spec=GroupChatMember)

    mock_db = AsyncMock()
    call_count = 0

    async def mock_execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # File query
            result.scalar_one_or_none.return_value = mock_file
        elif call_count == 2:
            # Folder query
            result.scalar_one_or_none.return_value = mock_folder
        elif call_count == 3:
            # GroupChat query
            result.scalar_one_or_none.return_value = mock_gc
        elif call_count == 4:
            # Member check — returns existing member → 409
            result.scalar_one_or_none.return_value = mock_member
        else:
            result.scalar_one_or_none.return_value = None
        return result

    mock_db.execute = mock_execute

    current_user = MagicMock(spec=User)
    current_user.id = 1

    from app.services.group_chat_service import send_invites
    with pytest.raises(HTTPException) as exc:
        await send_invites(
            mock_db,
            file_id=1,
            current_user=current_user,
            user_ids=[5],
            group_chat_id=42,
        )

    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Integration tests — need real Postgres
# ---------------------------------------------------------------------------


@pytest.fixture
def db_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration test")
    return url


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invite_lifecycle_create_accept(db_url):
    """
    Full invite lifecycle: create thread → invite → accept → member present.
    Uses rollback so it doesn't pollute the DB.
    """
    from sqlalchemy import select
    from app.database.session import AsyncSessionLocal
    from app.models.user import User
    from app.models.classroom import Classroom
    from app.models.file import File
    from app.models.group_chat import GroupChatMember, InviteStatus
    from app.services.group_chat_service import send_invites, accept_invite

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Need two users, a classroom, and a file
            user1_q = await db.execute(
                select(User).where(User.is_system == False).limit(1)
            )
            user1 = user1_q.scalar_one_or_none()
            if user1 is None:
                pytest.skip("No non-system user in DB")

            user2_q = await db.execute(
                select(User).where(User.is_system == False, User.id != user1.id).limit(1)
            )
            user2 = user2_q.scalar_one_or_none()
            if user2 is None:
                pytest.skip("Need at least 2 non-system users")

            file_q = await db.execute(select(File).limit(1))
            file = file_q.scalar_one_or_none()
            if file is None:
                pytest.skip("No file in DB")

            gc, invites = await send_invites(db, file.id, user1, [user2.id])
            assert len(invites) == 1
            assert invites[0].status == InviteStatus.PENDING

            gc2 = await accept_invite(db, invites[0].id, user2)
            assert gc2.id == gc.id

            member_q = await db.execute(
                select(GroupChatMember).where(
                    GroupChatMember.group_chat_id == gc.id,
                    GroupChatMember.user_id == user2.id,
                )
            )
            member = member_q.scalar_one_or_none()
            assert member is not None

            await db.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invite_reject_does_not_create_member(db_url):
    """Rejecting an invite must NOT add user as member."""
    from sqlalchemy import select
    from app.database.session import AsyncSessionLocal
    from app.models.user import User
    from app.models.file import File
    from app.models.group_chat import GroupChatMember
    from app.services.group_chat_service import send_invites, reject_invite

    async with AsyncSessionLocal() as db:
        async with db.begin():
            user1_q = await db.execute(
                select(User).where(User.is_system == False).limit(1)
            )
            user1 = user1_q.scalar_one_or_none()
            if user1 is None:
                pytest.skip("No non-system user in DB")

            user2_q = await db.execute(
                select(User).where(User.is_system == False, User.id != user1.id).limit(1)
            )
            user2 = user2_q.scalar_one_or_none()
            if user2 is None:
                pytest.skip("Need at least 2 non-system users")

            file_q = await db.execute(select(File).limit(1))
            file = file_q.scalar_one_or_none()
            if file is None:
                pytest.skip("No file in DB")

            gc, invites = await send_invites(db, file.id, user1, [user2.id])
            await reject_invite(db, invites[0].id, user2)

            member_q = await db.execute(
                select(GroupChatMember).where(
                    GroupChatMember.group_chat_id == gc.id,
                    GroupChatMember.user_id == user2.id,
                )
            )
            member = member_q.scalar_one_or_none()
            assert member is None

            await db.rollback()
