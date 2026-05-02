"""
Mention parsing for group chat messages.
Mentions are parsed and stored at write time — never re-parsed from content.
"""
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.group_chat import GroupChatMember
from app.models.user import User

MENTION_RE = re.compile(r"@(\w+)")


async def parse_mentions(
    content: str, group_chat_id: int, db: AsyncSession
) -> list[dict]:
    """
    Extract @mention tokens from content, resolving them against thread members.

    Returns a list of dicts:
      - {"kind": "agent", "username": "SAMpai"} for @SAMpai
      - {"kind": "user", "user_id": <id>, "username": <username>} for known members
    Unresolved tokens are silently dropped.
    Duplicate mentions of the same target are deduplicated.
    """
    candidates = MENTION_RE.findall(content)
    if not candidates:
        return []

    result = await db.execute(
        select(User)
        .join(GroupChatMember, GroupChatMember.user_id == User.id)
        .where(GroupChatMember.group_chat_id == group_chat_id)
    )
    members = result.scalars().all()
    by_username = {m.username.lower(): m for m in members}

    out = []
    seen: set[str] = set()
    for token in candidates:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        if key == "sampai":
            out.append({"kind": "agent", "username": "SAMpai"})
        elif key in by_username:
            u = by_username[key]
            out.append({"kind": "user", "user_id": u.id, "username": u.username})

    return out
