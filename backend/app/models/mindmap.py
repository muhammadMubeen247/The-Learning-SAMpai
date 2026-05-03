import enum
from datetime import datetime

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database.base import Base


class MindmapStatus(str, enum.Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class MindmapMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    MARKER = "marker"


class Mindmap(Base):
    __tablename__ = "mindmaps"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        Integer,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    classroom_id = Column(
        Integer,
        ForeignKey("classrooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    root_topic = Column(String(120), nullable=True)
    root_description = Column(Text, nullable=True)
    tree_data = Column(JSONB, nullable=False, default=dict)
    status = Column(
        SQLEnum(MindmapStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MindmapStatus.PENDING,
    )
    error_message = Column(String(500), nullable=True)
    node_count = Column(Integer, nullable=False, default=0)
    generation_meta = Column(JSONB, nullable=True, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    node_chats = relationship(
        "MindmapNodeChat",
        back_populates="mindmap",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_mindmap_classroom_status", "classroom_id", "status"),
    )


class MindmapNodeChat(Base):
    __tablename__ = "mindmap_node_chats"

    id = Column(Integer, primary_key=True, index=True)
    mindmap_id = Column(
        Integer,
        ForeignKey("mindmaps.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id = Column(String(64), nullable=True)
    role = Column(
        SQLEnum(MindmapMessageRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    # NOTE: named message_metadata (not metadata) because `metadata` is
    # reserved on SQLAlchemy's declarative Base.
    message_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    mindmap = relationship("Mindmap", back_populates="node_chats")

    __table_args__ = (
        Index("idx_mindmap_chat_user_time", "mindmap_id", "user_id", "created_at"),
        Index("idx_mindmap_chat_node", "mindmap_id", "user_id", "node_id"),
    )
