from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Any
from app.models.group_chat import GroupRole, InviteStatus, GroupMessageRole


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    group_chat_id: int
    user_id: int
    role: GroupRole
    joined_at: datetime
    last_read_seq: int
    user: UserSummary


class GroupChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_id: int
    classroom_id: int
    created_by: Optional[int]
    name: Optional[str]
    is_archived: bool
    created_at: datetime
    members: list[MemberOut] = []


class ThreadListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_id: int
    name: Optional[str]
    is_archived: bool
    unread_count: int = 0
    last_message_preview: Optional[str] = None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_chat_id: int
    inviter_id: int
    invitee_id: int
    status: InviteStatus
    created_at: datetime
    responded_at: Optional[datetime]
    inviter: UserSummary
    invitee: UserSummary


class InviteIn(BaseModel):
    user_ids: list[int]
    group_chat_id: Optional[int] = None


class GroupMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    group_chat_id: int
    seq: int
    user_id: Optional[int]
    role: GroupMessageRole
    content: str
    mentions: list
    reply_to_id: Optional[int]
    is_discarded: bool
    discard_reason: Optional[str]
    client_msg_id: Optional[Any]
    created_at: datetime
    author: Optional[UserSummary] = None


class SendMessageIn(BaseModel):
    content: str
    reply_to_id: Optional[int] = None
    client_msg_id: Optional[str] = None


class ReadReceiptIn(BaseModel):
    last_seq: int


class FileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_url: str
