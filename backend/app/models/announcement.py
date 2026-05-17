from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from app.database.base import Base


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    classroom_id = Column(
        Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)  # HTML from rich text editor
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    classroom = relationship("Classroom")
    created_by = relationship("User", foreign_keys=[created_by_id])
    comments = relationship(
        "AnnouncementComment",
        back_populates="announcement",
        cascade="all, delete-orphan",
        order_by="AnnouncementComment.created_at",
    )

    __table_args__ = (
        Index("idx_announcement_classroom_id", "classroom_id"),
        Index("idx_announcement_created_at", "created_at"),
    )


class AnnouncementComment(Base):
    __tablename__ = "announcement_comments"

    id = Column(Integer, primary_key=True, index=True)
    announcement_id = Column(
        Integer, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    announcement = relationship("Announcement", back_populates="comments")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (Index("idx_comment_announcement_id", "announcement_id"),)
