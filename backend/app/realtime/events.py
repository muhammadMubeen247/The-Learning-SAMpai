"""
WebSocket event models for the group chat real-time system.
All events use v=1 versioning and a Literal type discriminator.
"""
from typing import Any, Literal, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Per-thread events
# ---------------------------------------------------------------------------

class MessageNewEvent(BaseModel):
    v: int = 1
    type: Literal["message_new"] = "message_new"
    message: dict  # GroupMessageOut serialized


class MessageDiscardedEvent(BaseModel):
    v: int = 1
    type: Literal["message_discarded"] = "message_discarded"
    message_id: int
    reason: str


class AgentTypingEvent(BaseModel):
    v: int = 1
    type: Literal["agent_typing"] = "agent_typing"
    thread_id: int
    is_typing: bool


class MemberJoinedEvent(BaseModel):
    v: int = 1
    type: Literal["member_joined"] = "member_joined"
    thread_id: int
    user_id: int
    username: str


class MemberLeftEvent(BaseModel):
    v: int = 1
    type: Literal["member_left"] = "member_left"
    thread_id: int
    user_id: int


class PresenceEvent(BaseModel):
    v: int = 1
    type: Literal["presence"] = "presence"
    thread_id: int
    online_user_ids: list[int]


class TypingEvent(BaseModel):
    v: int = 1
    type: Literal["typing"] = "typing"
    thread_id: int
    user_id: int
    username: str = ""
    is_typing: bool


class ReadReceiptEvent(BaseModel):
    v: int = 1
    type: Literal["read_receipt"] = "read_receipt"
    thread_id: int
    user_id: int
    last_seq: int


# ---------------------------------------------------------------------------
# User-level events (delivered via /ws/user channel)
# ---------------------------------------------------------------------------

class InviteNewEvent(BaseModel):
    v: int = 1
    type: Literal["invite_new"] = "invite_new"
    invite: dict  # InviteOut serialized


class InviteCancelledEvent(BaseModel):
    v: int = 1
    type: Literal["invite_cancelled"] = "invite_cancelled"
    invite_id: int
    group_chat_id: int


class InviteAcceptedEvent(BaseModel):
    v: int = 1
    type: Literal["invite_accepted"] = "invite_accepted"
    invite_id: int
    group_chat_id: int
    user_id: int


class ThreadUnreadBumpEvent(BaseModel):
    v: int = 1
    type: Literal["thread_unread_bump"] = "thread_unread_bump"
    thread_id: int
    unread_count: int
