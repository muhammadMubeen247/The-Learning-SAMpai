from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database.base import Base
from datetime import datetime
import enum

class MessageRole(str, enum.Enum):
    """Enum for chat message roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Optional: Store metadata like tokens used, sources cited
    message_metadata = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    topic = relationship("Topic", back_populates="chat_messages")
    user = relationship("User")