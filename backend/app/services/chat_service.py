"""
Chat Service — async database operations for chat messages.
"""
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.models.chat_message import ChatMessage, MessageRole
from app.schemas.chat import ChatMessageOut

logger = logging.getLogger(__name__)


async def save_chat_message(
    db: AsyncSession,
    file_id: int,
    user_id: int,
    role: MessageRole,
    content: str,
    metadata: Optional[str] = None,
) -> ChatMessage:
    message = ChatMessage(
        file_id=file_id,
        user_id=user_id,
        role=role,
        content=content,
        message_metadata=metadata,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    logger.info(f"Saved {role.value} message for file {file_id}")
    return message


async def get_chat_history(
    db: AsyncSession,
    file_id: int,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> List[ChatMessageOut]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.file_id == file_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        ChatMessageOut(
            id=msg.id,
            file_id=msg.file_id,
            user_id=msg.user_id,
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
            metadata=msg.message_metadata if msg.message_metadata else None,
        )
        for msg in messages
    ]


async def delete_chat_history(db: AsyncSession, file_id: int, user_id: int) -> bool:
    try:
        await db.execute(
            delete(ChatMessage).where(
                ChatMessage.file_id == file_id,
                ChatMessage.user_id == user_id,
            )
        )
        await db.commit()
        logger.info(f"Deleted chat history for file {file_id}, user {user_id}")
        return True
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting chat history: {e}")
        return False


async def get_conversation_history_for_rag(
    db: AsyncSession,
    file_id: int,
    user_id: int,
    limit: int = 10,
) -> list[dict]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.file_id == file_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        {"role": msg.role.value, "content": msg.content}
        for msg in reversed(messages)
    ]


async def get_chat_statistics(db: AsyncSession, file_id: int) -> dict:
    total = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.file_id == file_id)
    )
    user_msgs = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.file_id == file_id,
            ChatMessage.role == MessageRole.USER,
        )
    )
    return {
        "total_messages": total,
        "user_questions": user_msgs,
        "assistant_responses": total - user_msgs,
    }
