from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base

class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    topic_name = Column(String(500), nullable=False)
    introduction = Column(Text, nullable=True)  # Brief description of topic
    order = Column(Integer, nullable=False, default=0)  # Display order in file
    
    # Relationships
    file = relationship("File", back_populates="topics")
    chat_messages = relationship("ChatMessage", back_populates="topic", cascade="all, delete-orphan")