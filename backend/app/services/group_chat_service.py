"""
Group chat service — thread management, invites, messages.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.classroom import Classroom, classroom_members
from app.models.file import File
from app.models.folder import Folder
from app.models.group_chat import (
    GroupChat,
    GroupChatInvite,
    GroupChatMember,
    GroupChatMessage,
    GroupMessageRole,
    GroupRole,
    InviteStatus,
)
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread management
# ---------------------------------------------------------------------------


async def create_thread(
    db: AsyncSession, file_id: int, classroom_id: int, creator_id: int
) -> GroupChat:
    """Create a new group chat thread, auto-naming it from the file."""
    # Load file to get filename
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    name = f"{file.filename} — group"

    gc = GroupChat(
        file_id=file_id,
        classroom_id=classroom_id,
        created_by=creator_id,
        name=name,
    )
    db.add(gc)
    await db.flush()

    # Creator becomes OWNER member
    member = GroupChatMember(
        group_chat_id=gc.id,
        user_id=creator_id,
        role=GroupRole.OWNER,
    )
    db.add(member)
    await db.flush()

    # Re-query with relationships
    result = await db.execute(
        select(GroupChat)
        .where(GroupChat.id == gc.id)
        .options(
            selectinload(GroupChat.members).selectinload(GroupChatMember.user),
        )
    )
    return result.scalar_one()


async def get_thread(
    db: AsyncSession, group_chat_id: int, user_id: int
) -> GroupChat:
    """Load thread with membership check."""
    result = await db.execute(
        select(GroupChat)
        .where(GroupChat.id == group_chat_id)
        .options(
            selectinload(GroupChat.members).selectinload(GroupChatMember.user),
        )
    )
    gc = result.scalar_one_or_none()
    if gc is None:
        raise HTTPException(status_code=404, detail="Group chat not found")

    member_ids = {m.user_id for m in gc.members}
    if user_id not in member_ids:
        raise HTTPException(
            status_code=403, detail="You are not a member of this group chat"
        )
    return gc


async def list_threads_for_user(db: AsyncSession, user_id: int) -> list[dict]:
    """List threads where user is a member, with unread counts."""
    result = await db.execute(
        select(GroupChatMember, GroupChat)
        .join(GroupChat, GroupChatMember.group_chat_id == GroupChat.id)
        .where(GroupChatMember.user_id == user_id)
        .options(selectinload(GroupChatMember.group_chat))
    )
    rows = result.all()

    threads = []
    for member_row, gc in rows:
        # Compute unread count
        max_seq_result = await db.execute(
            select(func.max(GroupChatMessage.seq)).where(
                GroupChatMessage.group_chat_id == gc.id,
                GroupChatMessage.is_discarded == False,
            )
        )
        max_seq = max_seq_result.scalar() or 0
        unread = max(0, max_seq - member_row.last_read_seq)

        # Get last message preview
        last_msg_result = await db.execute(
            select(GroupChatMessage)
            .where(
                GroupChatMessage.group_chat_id == gc.id,
                GroupChatMessage.is_discarded == False,
            )
            .order_by(GroupChatMessage.seq.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        preview = last_msg.content[:100] if last_msg else None

        threads.append(
            {
                "id": gc.id,
                "file_id": gc.file_id,
                "name": gc.name,
                "is_archived": gc.is_archived,
                "unread_count": unread,
                "last_message_preview": preview,
            }
        )
    return threads


async def leave_thread(db: AsyncSession, group_chat_id: int, user_id: int) -> None:
    """Remove user from thread; archive if empty."""
    result = await db.execute(
        select(GroupChatMember).where(
            GroupChatMember.group_chat_id == group_chat_id,
            GroupChatMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=404, detail="You are not a member of this group chat"
        )
    await db.delete(member)
    await db.flush()
    await archive_if_empty(db, group_chat_id)


async def archive_if_empty(db: AsyncSession, group_chat_id: int) -> None:
    """Archive thread if no human members remain."""
    # Count non-system members
    result = await db.execute(
        select(func.count())
        .select_from(GroupChatMember)
        .join(User, User.id == GroupChatMember.user_id)
        .where(
            GroupChatMember.group_chat_id == group_chat_id,
            User.is_system == False,
        )
    )
    count = result.scalar() or 0
    if count == 0:
        gc = await db.get(GroupChat, group_chat_id)
        if gc:
            gc.is_archived = True
            db.add(gc)
            await db.flush()


async def update_read_seq(
    db: AsyncSession, group_chat_id: int, user_id: int, last_seq: int
) -> None:
    """Advance last_read_seq for a member (never go backwards)."""
    result = await db.execute(
        select(GroupChatMember).where(
            GroupChatMember.group_chat_id == group_chat_id,
            GroupChatMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=403, detail="You are not a member of this group chat"
        )
    if last_seq > member.last_read_seq:
        member.last_read_seq = last_seq
        db.add(member)
        await db.flush()


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


async def list_eligible(
    db: AsyncSession,
    file_id: int,
    current_user_id: int,
    group_chat_id: int | None = None,
) -> list[User]:
    """
    Return classroom members eligible to be invited to a group chat thread.
    Excludes: self, system users, current members, pending invitees.
    """
    # Resolve classroom from file
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()
    classroom_id = folder.classroom_id

    q = (
        select(User)
        .join(classroom_members, classroom_members.c.user_id == User.id)
        .where(
            classroom_members.c.classroom_id == classroom_id,
            User.id != current_user_id,
            User.is_system == False,
        )
    )

    if group_chat_id is not None:
        # Exclude existing members
        existing_members_sq = select(GroupChatMember.user_id).where(
            GroupChatMember.group_chat_id == group_chat_id
        )
        # Exclude pending invitees
        pending_invitees_sq = select(GroupChatInvite.invitee_id).where(
            GroupChatInvite.group_chat_id == group_chat_id,
            GroupChatInvite.status == InviteStatus.PENDING,
        )
        q = q.where(
            User.id.not_in(existing_members_sq),
            User.id.not_in(pending_invitees_sq),
        )

    result = await db.execute(q)
    return list(result.scalars().all())


async def send_invites(
    db: AsyncSession,
    file_id: int,
    current_user: User,
    user_ids: list[int],
    group_chat_id: int | None = None,
) -> tuple[GroupChat, list[GroupChatInvite]]:
    """Create invites, creating a thread if needed."""
    # Resolve classroom from file
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()
    classroom_id = folder.classroom_id

    # Create thread if not specified
    if group_chat_id is None:
        gc = await create_thread(db, file_id, classroom_id, current_user.id)
        group_chat_id = gc.id
    else:
        result = await db.execute(
            select(GroupChat)
            .where(GroupChat.id == group_chat_id)
            .options(selectinload(GroupChat.members).selectinload(GroupChatMember.user))
        )
        gc = result.scalar_one_or_none()
        if gc is None:
            raise HTTPException(status_code=404, detail="Group chat not found")

    # Validate each invitee
    invites = []
    for uid in user_ids:
        # Check not already a member
        member_result = await db.execute(
            select(GroupChatMember).where(
                GroupChatMember.group_chat_id == group_chat_id,
                GroupChatMember.user_id == uid,
            )
        )
        if member_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"User {uid} is already a member of this group chat",
            )

        # Check no pending invite already
        invite_result = await db.execute(
            select(GroupChatInvite).where(
                GroupChatInvite.group_chat_id == group_chat_id,
                GroupChatInvite.invitee_id == uid,
                GroupChatInvite.status == InviteStatus.PENDING,
            )
        )
        if invite_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A pending invite already exists for user {uid}",
            )

        invite = GroupChatInvite(
            group_chat_id=group_chat_id,
            inviter_id=current_user.id,
            invitee_id=uid,
            status=InviteStatus.PENDING,
        )
        db.add(invite)
        invites.append(invite)

    await db.flush()

    # Reload invites with relationships
    loaded_invites = []
    for inv in invites:
        result = await db.execute(
            select(GroupChatInvite)
            .where(GroupChatInvite.id == inv.id)
            .options(
                selectinload(GroupChatInvite.inviter),
                selectinload(GroupChatInvite.invitee),
            )
        )
        loaded_invites.append(result.scalar_one())

    return gc, loaded_invites


async def accept_invite(
    db: AsyncSession, invite_id: int, current_user: User
) -> GroupChat:
    """Accept a pending invite, adding the user as a MEMBER."""
    result = await db.execute(
        select(GroupChatInvite)
        .where(GroupChatInvite.id == invite_id)
        .options(
            selectinload(GroupChatInvite.inviter),
            selectinload(GroupChatInvite.invitee),
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.invitee_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the invitee for this invite"
        )
    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"Invite is already {invite.status.value}"
        )

    invite.status = InviteStatus.ACCEPTED
    invite.responded_at = datetime.utcnow()
    db.add(invite)

    member = GroupChatMember(
        group_chat_id=invite.group_chat_id,
        user_id=current_user.id,
        role=GroupRole.MEMBER,
    )
    db.add(member)
    await db.flush()

    return await get_thread(db, invite.group_chat_id, current_user.id)


async def reject_invite(
    db: AsyncSession, invite_id: int, current_user: User
) -> GroupChatInvite:
    """Reject a pending invite."""
    result = await db.execute(
        select(GroupChatInvite)
        .where(GroupChatInvite.id == invite_id)
        .options(
            selectinload(GroupChatInvite.inviter),
            selectinload(GroupChatInvite.invitee),
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.invitee_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You are not the invitee for this invite"
        )
    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"Invite is already {invite.status.value}"
        )

    invite.status = InviteStatus.REJECTED
    invite.responded_at = datetime.utcnow()
    db.add(invite)
    await db.flush()
    return invite


async def cancel_invite(
    db: AsyncSession, invite_id: int, current_user: User
) -> GroupChatInvite:
    """Cancel an invite. Only the inviter can cancel."""
    result = await db.execute(
        select(GroupChatInvite)
        .where(GroupChatInvite.id == invite_id)
        .options(
            selectinload(GroupChatInvite.inviter),
            selectinload(GroupChatInvite.invitee),
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.inviter_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the inviter can cancel an invite"
        )
    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"Invite is already {invite.status.value}"
        )

    invite.status = InviteStatus.CANCELLED
    invite.responded_at = datetime.utcnow()
    db.add(invite)
    await db.flush()
    return invite


async def get_pending_invites(
    db: AsyncSession, user_id: int
) -> list[GroupChatInvite]:
    """Return all pending invites for a user."""
    result = await db.execute(
        select(GroupChatInvite)
        .where(
            GroupChatInvite.invitee_id == user_id,
            GroupChatInvite.status == InviteStatus.PENDING,
        )
        .options(
            selectinload(GroupChatInvite.inviter),
            selectinload(GroupChatInvite.invitee),
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def send_message(
    db: AsyncSession,
    thread_id: int,
    user_id: int | None,
    content: str,
    reply_to_id: int | None = None,
    client_msg_id: str | None = None,
    role: GroupMessageRole = GroupMessageRole.USER,
) -> GroupChatMessage:
    """Insert a message, honouring idempotency via client_msg_id."""
    import uuid as _uuid

    # Parse client_msg_id as UUID if provided
    parsed_client_msg_id = None
    if client_msg_id:
        try:
            parsed_client_msg_id = _uuid.UUID(client_msg_id)
        except (ValueError, AttributeError):
            parsed_client_msg_id = None

    # Idempotency check
    if parsed_client_msg_id is not None:
        existing_result = await db.execute(
            select(GroupChatMessage)
            .where(
                GroupChatMessage.group_chat_id == thread_id,
                GroupChatMessage.client_msg_id == parsed_client_msg_id,
            )
            .options(
                selectinload(GroupChatMessage.reply_to),
                selectinload(GroupChatMessage.author),
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

    # Parse mentions
    from app.services.mentions import parse_mentions
    mentions = await parse_mentions(content, thread_id, db)

    # Serialize seq with FOR UPDATE lock on group_chats row
    gc_result = await db.execute(
        select(GroupChat)
        .where(GroupChat.id == thread_id)
        .with_for_update()
    )
    gc = gc_result.scalar_one_or_none()
    if gc is None:
        raise HTTPException(status_code=404, detail="Group chat not found")

    # Get next seq
    seq_result = await db.execute(
        select(func.coalesce(func.max(GroupChatMessage.seq), 0) + 1).where(
            GroupChatMessage.group_chat_id == thread_id
        )
    )
    next_seq = seq_result.scalar()

    msg = GroupChatMessage(
        group_chat_id=thread_id,
        seq=next_seq,
        user_id=user_id,
        role=role,
        content=content,
        mentions=mentions,
        reply_to_id=reply_to_id,
        client_msg_id=parsed_client_msg_id,
    )
    db.add(msg)
    await db.flush()
    await db.commit()

    # Re-query with relationships
    result = await db.execute(
        select(GroupChatMessage)
        .where(GroupChatMessage.id == msg.id)
        .options(
            selectinload(GroupChatMessage.reply_to),
            selectinload(GroupChatMessage.author),
        )
    )
    return result.scalar_one()


async def list_messages(
    db: AsyncSession,
    thread_id: int,
    before_seq: int | None = None,
    limit: int = 50,
) -> list[GroupChatMessage]:
    """Fetch messages older than before_seq, ascending order."""
    q = (
        select(GroupChatMessage)
        .where(
            GroupChatMessage.group_chat_id == thread_id,
            GroupChatMessage.is_discarded == False,
        )
        .options(
            selectinload(GroupChatMessage.reply_to),
            selectinload(GroupChatMessage.author),
        )
    )
    if before_seq is not None:
        q = q.where(GroupChatMessage.seq < before_seq)
    q = q.order_by(GroupChatMessage.seq.desc()).limit(limit)

    result = await db.execute(q)
    return list(reversed(result.scalars().all()))
