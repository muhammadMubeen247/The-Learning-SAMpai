import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class GroupRole(str, enum.Enum):
    OWNER = "owner"
    MEMBER = "member"


class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class GroupMessageRole(str, enum.Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class GroupChat(Base):
    __tablename__ = "group_chats"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(120), nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    file = relationship("File")
    classroom = relationship("Classroom")
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("GroupChatMember", back_populates="group_chat", cascade="all, delete-orphan")
    invites = relationship("GroupChatInvite", back_populates="group_chat", cascade="all, delete-orphan")
    messages = relationship("GroupChatMessage", back_populates="group_chat", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_gc_file_archived", "file_id", "is_archived"),
        Index("idx_gc_classroom", "classroom_id"),
    )


class GroupChatMember(Base):
    __tablename__ = "group_chat_members"

    group_chat_id = Column(
        Integer, ForeignKey("group_chats.id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(SQLEnum(GroupRole, values_callable=lambda x: [e.value for e in x]), nullable=False)
    joined_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_read_seq = Column(BigInteger, nullable=False, default=0)

    group_chat = relationship("GroupChat", back_populates="members")
    user = relationship("User")


class GroupChatInvite(Base):
    __tablename__ = "group_chat_invites"

    id = Column(Integer, primary_key=True, index=True)
    group_chat_id = Column(
        Integer, ForeignKey("group_chats.id", ondelete="CASCADE"), nullable=False
    )
    inviter_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(
        SQLEnum(InviteStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=InviteStatus.PENDING,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)

    group_chat = relationship("GroupChat", back_populates="invites")
    inviter = relationship("User", foreign_keys=[inviter_id])
    invitee = relationship("User", foreign_keys=[invitee_id])

    __table_args__ = (
        UniqueConstraint("group_chat_id", "invitee_id", name="uq_gc_invite_per_invitee"),
    )


class GroupChatMessage(Base):
    __tablename__ = "group_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    group_chat_id = Column(
        Integer, ForeignKey("group_chats.id", ondelete="CASCADE"), nullable=False
    )
    seq = Column(BigInteger, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role = Column(
        SQLEnum(GroupMessageRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    mentions = Column(JSONB, nullable=False, default=list)
    reply_to_id = Column(
        Integer,
        ForeignKey("group_chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_discarded = Column(Boolean, nullable=False, default=False)
    discard_reason = Column(String(255), nullable=True)
    client_msg_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    group_chat = relationship("GroupChat", back_populates="messages")
    author = relationship("User")
    reply_to = relationship("GroupChatMessage", remote_side="GroupChatMessage.id")

    __table_args__ = (
        UniqueConstraint("group_chat_id", "seq", name="uq_gc_message_seq"),
        Index("idx_gcm_group_created", "group_chat_id", "created_at"),
        Index("idx_gcm_group_user", "group_chat_id", "user_id"),
    )
