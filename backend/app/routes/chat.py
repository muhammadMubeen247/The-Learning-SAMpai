import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists, func
from typing import List

from app.database.session import get_db
from app.models.file import File, ProcessingStatus
from app.models.folder import Folder
from app.models.classroom import Classroom, classroom_members
from app.models.chat_message import ChatMessage, MessageRole
from app.schemas.chat import (
    QuestionRequest,
    QuestionResponse,
    ChatMessageOut,
    ChatHistoryResponse,
    SourceInfo,
)
from app.dependencies.auth import get_current_user
from app.rag.base import QueryParam
from app.services.classroom_rag import classroom_rag_service
from app.services.chat_service import (
    save_chat_message,
    get_chat_history,
    delete_chat_history,
    get_chat_statistics,
    get_conversation_history_for_rag,
)

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


async def _get_file_and_classroom(file_id: int, current_user, db: AsyncSession):
    """Shared access-control helper: returns (file, classroom) or raises."""
    result = await db.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    result = await db.execute(select(Folder).where(Folder.id == file.folder_id))
    folder = result.scalar_one_or_none()

    result = await db.execute(select(Classroom).where(Classroom.id == folder.classroom_id))
    classroom = result.scalar_one_or_none()

    is_member = await db.scalar(
        select(exists().where(
            (classroom_members.c.classroom_id == classroom.id) &
            (classroom_members.c.user_id == current_user.id)
        ))
    )
    if not is_member:
        raise HTTPException(status_code=403, detail="You are not a member of this classroom")

    return file, classroom


@router.post("/files/{file_id}/ask", response_model=QuestionResponse)
async def ask_question(
    file_id: int,
    request: QuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(
        f"[chat] ASK file_id={file_id} user_id={current_user.id} "
        f"q_len={len(request.question)}"
    )

    file, classroom = await _get_file_and_classroom(file_id, current_user, db)

    if file.processing_status.value != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"File is still being processed. Status: {file.processing_status.value}",
        )

    history = await get_conversation_history_for_rag(
        db=db, file_id=file_id, user_id=current_user.id, limit=10,
    )

    try:
        engine = await classroom_rag_service.get_engine(classroom.id)
        param = QueryParam(
            mode="naive",
            chunk_top_k=20,
            conversation_history=history,
            file_filter=file.file_url,
        )
        query_result = await engine.aquery(request.question, param)
        answer = query_result.content or ""
        logger.info(f"[chat] ANSWER file_id={file_id} a_len={len(answer)}")
    except Exception as e:
        logger.error(f"[chat] ASK_FAIL file_id={file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating answer: {e}")

    sources = [
        SourceInfo(file_path=ref["file_path"])
        for ref in query_result.reference_list
        if ref.get("file_path")
    ]

    await save_chat_message(db=db, file_id=file_id, user_id=current_user.id,
                            role=MessageRole.USER, content=request.question)
    assistant_msg = await save_chat_message(
        db=db, file_id=file_id, user_id=current_user.id,
        role=MessageRole.ASSISTANT, content=answer,
        metadata=json.dumps({"mode": "mix", "sources_count": len(sources)}),
    )

    return QuestionResponse(
        answer=answer,
        sources=sources,
        confidence="high",
        chunks_used=len(sources),
        message_id=assistant_msg.id,
    )


@router.get("/files/{file_id}/history", response_model=ChatHistoryResponse)
async def get_file_chat_history(
    file_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(
        f"[chat] HISTORY file_id={file_id} user_id={current_user.id} "
        f"limit={limit} offset={offset}"
    )
    await _get_file_and_classroom(file_id, current_user, db)

    messages = await get_chat_history(
        db=db, file_id=file_id, user_id=current_user.id, limit=limit, offset=offset,
    )

    total = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(
            ChatMessage.file_id == file_id, ChatMessage.user_id == current_user.id,
        )
    )

    return ChatHistoryResponse(messages=messages, total=total, offset=offset, limit=limit)


@router.delete("/files/{file_id}/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_chat_history(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(f"[chat] CLEAR_HISTORY file_id={file_id} user_id={current_user.id}")
    await _get_file_and_classroom(file_id, current_user, db)

    success = await delete_chat_history(db=db, file_id=file_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear history")

    return None


@router.get("/files/{file_id}/stats")
async def get_file_stats(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    file, _ = await _get_file_and_classroom(file_id, current_user, db)
    stats = await get_chat_statistics(db=db, file_id=file_id)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "retrieval_mode": "mix",
        **stats,
    }
