"""
Chat Service
Handles database operations for chat messages
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.chat_message import ChatMessage, MessageRole
from app.models.topic import Topic
from app.schemas.chat import ChatMessageOut

logger = logging.getLogger(__name__)


def save_chat_message(
    db: Session,
    topic_id: int,
    user_id: int,
    role: MessageRole,
    content: str,
    metadata: Optional[str] = None
) -> ChatMessage:
    """
    Save a chat message to database
    
    Args:
        db: Database session
        topic_id: Topic this message belongs to
        user_id: User who sent/received the message
        role: Message role (user/assistant/system)
        content: Message content
        metadata: Optional JSON metadata
        
    Returns:
        Created ChatMessage object
    """
    try:
        message = ChatMessage(
            topic_id=topic_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata
        )
        
        db.add(message)
        db.commit()
        db.refresh(message)
        
        logger.info(f"Saved {role.value} message for topic {topic_id}")
        
        return message
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving chat message: {str(e)}")
        raise


def get_chat_history(
    db: Session,
    topic_id: int,
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[ChatMessage]:
    """
    Get chat history for a topic
    
    Args:
        db: Database session
        topic_id: Topic ID
        user_id: User ID (for access control)
        limit: Max messages to return
        offset: Pagination offset
        
    Returns:
        List of ChatMessage objects
    """
    messages = db.query(ChatMessage).filter(
        ChatMessage.topic_id == topic_id,
        ChatMessage.user_id == user_id
    ).order_by(
        ChatMessage.timestamp.asc()
    ).offset(offset).limit(limit).all()
    
    return [
        ChatMessageOut(
            id=msg.id,
            topic_id=msg.topic_id,
            user_id=msg.user_id,
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
            metadata=msg.message_metadata if msg.message_metadata else None
        )
        for msg in messages
    ]


def delete_chat_history(
    db: Session,
    topic_id: int,
    user_id: int
) -> bool:
    """
    Delete all chat messages for a topic and user
    
    Args:
        db: Database session
        topic_id: Topic ID
        user_id: User ID
        
    Returns:
        True if successful
    """
    try:
        db.query(ChatMessage).filter(
            ChatMessage.topic_id == topic_id,
            ChatMessage.user_id == user_id
        ).delete()
        
        db.commit()
        logger.info(f"Deleted chat history for topic {topic_id}, user {user_id}")
        
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting chat history: {str(e)}")
        return False


def get_chat_statistics(
    db: Session,
    topic_id: int
) -> dict:
    """
    Get statistics about chat for a topic
    
    Args:
        db: Database session
        topic_id: Topic ID
        
    Returns:
        Dictionary with statistics
    """
    total_messages = db.query(ChatMessage).filter(
        ChatMessage.topic_id == topic_id
    ).count()
    
    user_messages = db.query(ChatMessage).filter(
        ChatMessage.topic_id == topic_id,
        ChatMessage.role == MessageRole.USER
    ).count()
    
    return {
        "total_messages": total_messages,
        "user_questions": user_messages,
        "assistant_responses": total_messages - user_messages
    }