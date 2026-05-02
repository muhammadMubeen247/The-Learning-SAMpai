"""
Group chat context helpers — fetch recent messages for agent context building.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.group_chat import GroupChatMessage


async def fetch_recent_messages(
    db: AsyncSession,
    thread_id: int,
    limit: int = 12,
    before_id: int | None = None,
) -> list[GroupChatMessage]:
    """
    Fetch the most recent non-discarded messages from a thread.

    CRITICAL: always filters WHERE is_discarded = False so agent context
    never includes content that was removed by the guard.
    """
    q = (
        select(GroupChatMessage)
        .where(
            GroupChatMessage.group_chat_id == thread_id,
            GroupChatMessage.is_discarded == False,  # CRITICAL — never skip
        )
        .order_by(GroupChatMessage.seq.desc())
        .limit(limit)
        .options(selectinload(GroupChatMessage.author))
    )
    if before_id is not None:
        q = q.where(GroupChatMessage.id < before_id)

    result = await db.execute(q)
    return list(reversed(result.scalars().all()))


async def fetch_last_messages_from_user(
    db: AsyncSession,
    thread_id: int,
    user_id: int,
    limit: int = 3,
) -> list[GroupChatMessage]:
    """
    Fetch the last N non-discarded messages from a specific user in a thread.

    CRITICAL: always filters WHERE is_discarded = False.
    """
    result = await db.execute(
        select(GroupChatMessage)
        .where(
            GroupChatMessage.group_chat_id == thread_id,
            GroupChatMessage.user_id == user_id,
            GroupChatMessage.is_discarded == False,  # CRITICAL filter
        )
        .order_by(GroupChatMessage.seq.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
