"""
LangChain Memory Backend
Custom BaseChatMessageHistory that integrates with our database
Bridges LangChain's memory system with our chat_message model
"""

import logging
from typing import List
from sqlalchemy.orm import Session

# LangChain imports - FIXED IMPORT PATH
from langchain.schema import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage
)
# FIXED: BaseChatMessageHistory is in langchain_core.chat_history
from langchain_core.chat_history import BaseChatMessageHistory

# Our models
from app.models.chat_message import ChatMessage, MessageRole
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


class DatabaseChatMessageHistory(BaseChatMessageHistory):
    """
    Custom chat message history that stores messages in our database
    
    Implements LangChain's BaseChatMessageHistory interface while
    using our existing chat_message table for storage
    """
    
    def __init__(
        self,
        topic_id: int,
        user_id: int,
        db: Session = None
    ):
        """
        Initialize database message history
        
        Args:
            topic_id: Topic ID for this conversation
            user_id: User ID who owns this conversation
            db: Optional database session (creates new if not provided)
        """
        self.topic_id = topic_id
        self.user_id = user_id
        self._db = db
        self._owns_db = False
        
        # Create DB session if not provided
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        
        logger.debug(f"Initialized DatabaseChatMessageHistory for topic {topic_id}, user {user_id}")
    
    def _get_db(self) -> Session:
        """Get database session"""
        return self._db
    
    def _langchain_message_to_db_role(self, message: BaseMessage) -> MessageRole:
        """
        Convert LangChain message type to our MessageRole enum
        
        Args:
            message: LangChain message
            
        Returns:
            MessageRole enum value
        """
        if isinstance(message, HumanMessage):
            return MessageRole.USER
        elif isinstance(message, AIMessage):
            return MessageRole.ASSISTANT
        elif isinstance(message, SystemMessage):
            return MessageRole.SYSTEM
        else:
            # Default to user for unknown types
            logger.warning(f"Unknown message type: {type(message)}, defaulting to USER")
            return MessageRole.USER
    
    def _db_message_to_langchain(self, db_message: ChatMessage) -> BaseMessage:
        """
        Convert database ChatMessage to LangChain message
        
        Args:
            db_message: ChatMessage from database
            
        Returns:
            LangChain BaseMessage
        """
        content = db_message.content
        
        if db_message.role == MessageRole.USER:
            return HumanMessage(content=content)
        elif db_message.role == MessageRole.ASSISTANT:
            return AIMessage(content=content)
        elif db_message.role == MessageRole.SYSTEM:
            return SystemMessage(content=content)
        else:
            # Default to HumanMessage for unknown roles
            logger.warning(f"Unknown role: {db_message.role}, defaulting to HumanMessage")
            return HumanMessage(content=content)
    
    @property
    def messages(self) -> List[BaseMessage]:
        """
        Retrieve all messages for this conversation from database
        
        Returns:
            List of LangChain BaseMessage objects
        """
        db = self._get_db()
        
        # Query messages from database
        db_messages = db.query(ChatMessage).filter(
            ChatMessage.topic_id == self.topic_id,
            ChatMessage.user_id == self.user_id
        ).order_by(ChatMessage.timestamp.asc()).all()
        
        # Convert to LangChain messages
        langchain_messages = [
            self._db_message_to_langchain(msg) for msg in db_messages
        ]
        
        logger.debug(f"Retrieved {len(langchain_messages)} messages from database")
        
        return langchain_messages
    
    def add_message(self, message: BaseMessage) -> None:
        """
        Add a message to the database
        
        Args:
            message: LangChain message to add
        """
        db = self._get_db()
        
        # Convert to database format
        role = self._langchain_message_to_db_role(message)
        
        # Create database record
        db_message = ChatMessage(
            topic_id=self.topic_id,
            user_id=self.user_id,
            role=role,
            content=message.content
        )
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        logger.debug(f"Added {role.value} message to database (id: {db_message.id})")
    
    def add_user_message(self, message: str) -> None:
        """
        Add a user message
        
        Args:
            message: Message text
        """
        self.add_message(HumanMessage(content=message))
    
    def add_ai_message(self, message: str) -> None:
        """
        Add an AI message
        
        Args:
            message: Message text
        """
        self.add_message(AIMessage(content=message))
    
    def clear(self) -> None:
        """
        Clear all messages for this conversation from database
        """
        db = self._get_db()
        
        db.query(ChatMessage).filter(
            ChatMessage.topic_id == self.topic_id,
            ChatMessage.user_id == self.user_id
        ).delete()
        
        db.commit()
        
        logger.info(f"Cleared all messages for topic {self.topic_id}, user {self.user_id}")
    
    def __del__(self):
        """Close database session if we own it"""
        if self._owns_db and self._db:
            try:
                self._db.close()
            except:
                pass


def get_chat_memory_for_topic(
    topic_id: int,
    user_id: int,
    db: Session = None
) -> DatabaseChatMessageHistory:
    """
    Factory function to create chat memory for a topic
    
    Args:
        topic_id: Topic ID
        user_id: User ID
        db: Optional database session
        
    Returns:
        DatabaseChatMessageHistory instance
    """
    return DatabaseChatMessageHistory(
        topic_id=topic_id,
        user_id=user_id,
        db=db
    )