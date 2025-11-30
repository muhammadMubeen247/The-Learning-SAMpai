from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.models.topic import Topic
from app.models.file import File
from app.models.folder import Folder
from app.models.classroom import Classroom
from app.models.chat_message import MessageRole
from app.schemas.chat import (
    QuestionRequest,
    QuestionResponse,
    ChatMessageOut,
    ChatHistoryResponse,
    SourceInfo
)
from app.dependencies.auth import get_current_user

# OLD: from app.services.rag_service import rag_service
# NEW: LangChain RAG service
from app.services.langchain_rag_service import langchain_rag_service

from app.services.chat_service import (
    get_chat_history,
    delete_chat_history,
    get_chat_statistics
)

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/topics/{topic_id}/ask", response_model=QuestionResponse)
def ask_question(
    topic_id: int,
    request: QuestionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Ask a question about a topic using LangChain RAG chain
    
    Process:
    1. Verify user has access to topic
    2. Get topic's file and classroom context
    3. Create ConversationalRetrievalChain with database memory
    4. Chain automatically:
       - Retrieves relevant chunks
       - Loads conversation history from database
       - Generates answer using GPT
       - Saves question and answer to database
    """
    # Verify topic exists
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Get file and verify access
    file = db.query(File).filter(File.id == topic.file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
    if current_user not in classroom.members:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this classroom"
        )
    
    # Check if file processing is complete
    if file.processing_status.value != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"File is still being processed. Status: {file.processing_status.value}"
        )
    
    # Use LangChain RAG chain (with automatic memory management)
    try:
        result = langchain_rag_service.ask_question(
            classroom_id=classroom.id,
            topic_id=topic_id,
            user_id=current_user.id,
            question=request.question,
            db=db,
            file_id=request.file_id or file.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating answer: {str(e)}"
        )
    
    # Get the last assistant message ID for response
    # (LangChain automatically saved it via DatabaseChatMessageHistory)
    from app.models.chat_message import ChatMessage
    last_message = db.query(ChatMessage).filter(
        ChatMessage.topic_id == topic_id,
        ChatMessage.user_id == current_user.id,
        ChatMessage.role == MessageRole.ASSISTANT
    ).order_by(ChatMessage.timestamp.desc()).first()
    
    message_id = last_message.id if last_message else 0
    
    # Format response
    return QuestionResponse(
        answer=result["answer"],
        sources=[SourceInfo(**source) for source in result["sources"]],
        confidence=result["confidence"],
        chunks_used=result["chunks_used"],
        message_id=message_id
    )


@router.get("/topics/{topic_id}/history", response_model=ChatHistoryResponse)
def get_topic_chat_history(
    topic_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get chat history for a topic
    """
    # Verify topic exists and user has access
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    file = db.query(File).filter(File.id == topic.file_id).first()
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get messages
    messages = get_chat_history(
        db=db,
        topic_id=topic_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    # Get total count
    from app.models.chat_message import ChatMessage
    total = db.query(ChatMessage).filter(
        ChatMessage.topic_id == topic_id,
        ChatMessage.user_id == current_user.id
    ).count()
    
    return ChatHistoryResponse(
        messages=messages,
        total=total,
        offset=offset,
        limit=limit
    )


@router.delete("/topics/{topic_id}/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_chat_history(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Clear chat history for a topic
    """
    # Verify access
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    file = db.query(File).filter(File.id == topic.file_id).first()
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete history
    success = delete_chat_history(
        db=db,
        topic_id=topic_id,
        user_id=current_user.id
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to clear history")
    
    return None


@router.get("/topics/{topic_id}/stats")
def get_topic_stats(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get statistics about chat for a topic
    """
    # Verify access
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    file = db.query(File).filter(File.id == topic.file_id).first()
    folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
    classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
    if current_user not in classroom.members:
        raise HTTPException(status_code=403, detail="Access denied")
    
    stats = get_chat_statistics(db=db, topic_id=topic_id)
    
    return {
        "topic_id": topic_id,
        "topic_name": topic.topic_name,
        "using_langchain": True,  # Indicate we're using LangChain
        **stats
    }













#OLD CODE


# from fastapi import APIRouter, Depends, HTTPException, status
# from sqlalchemy.orm import Session
# from typing import List
# import json

# from app.database.session import get_db
# from app.models.topic import Topic
# from app.models.file import File
# from app.models.folder import Folder
# from app.models.classroom import Classroom
# from app.models.chat_message import MessageRole
# from app.schemas.chat import (
#     QuestionRequest,
#     QuestionResponse,
#     ChatMessageOut,
#     ChatHistoryResponse,
#     SourceInfo
# )
# from app.dependencies.auth import get_current_user
# from app.services.rag_service import rag_service
# from app.services.chat_service import (
#     save_chat_message,
#     get_chat_history,
#     delete_chat_history,
#     get_chat_statistics
# )

# router = APIRouter(prefix="/chat", tags=["Chat"])


# @router.post("/topics/{topic_id}/ask", response_model=QuestionResponse)
# def ask_question(
#     topic_id: int,
#     request: QuestionRequest,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Ask a question about a topic using RAG
    
#     Process:
#     1. Verify user has access to topic
#     2. Get topic's file and classroom context
#     3. Retrieve relevant chunks from vector store
#     4. Generate answer using GPT
#     5. Save question and answer to chat history
#     """
#     # Verify topic exists
#     topic = db.query(Topic).filter(Topic.id == topic_id).first()
#     if not topic:
#         raise HTTPException(status_code=404, detail="Topic not found")
    
#     # Get file and verify access
#     file = db.query(File).filter(File.id == topic.file_id).first()
#     if not file:
#         raise HTTPException(status_code=404, detail="File not found")
    
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
#     if current_user not in classroom.members:
#         raise HTTPException(
#             status_code=403,
#             detail="You are not a member of this classroom"
#         )
    
#     # Check if file processing is complete
#     if file.processing_status.value != "completed":
#         raise HTTPException(
#             status_code=400,
#             detail=f"File is still being processed. Status: {file.processing_status.value}"
#         )
    
#     # Get chat history for context
#     previous_messages = get_chat_history(
#         db=db,
#         topic_id=topic_id,
#         user_id=current_user.id,
#         limit=10  # Last 10 messages for context
#     )
    
#     # Convert to format expected by RAG service
#     chat_history = [
#         {
#             "role": msg.role.value,
#             "content": msg.content
#         }
#         for msg in previous_messages
#     ]
    
#     # Use RAG to answer question
#     try:
#         result = rag_service.ask_question(
#             classroom_id=classroom.id,
#             question=request.question,
#             file_id=request.file_id or file.id,
#             chat_history=chat_history,
#             top_k=5
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error generating answer: {str(e)}"
#         )
    
#     # Save user question
#     user_message = save_chat_message(
#         db=db,
#         topic_id=topic_id,
#         user_id=current_user.id,
#         role=MessageRole.USER,
#         content=request.question
#     )
    
#     # Save assistant response
#     metadata = json.dumps({
#         "confidence": result["confidence"],
#         "chunks_used": result["chunks_used"]
#     })
    
#     assistant_message = save_chat_message(
#         db=db,
#         topic_id=topic_id,
#         user_id=current_user.id,
#         role=MessageRole.ASSISTANT,
#         content=result["answer"],
#         metadata=metadata
#     )
    
#     # Format response
#     return QuestionResponse(
#         answer=result["answer"],
#         sources=[SourceInfo(**source) for source in result["sources"]],
#         confidence=result["confidence"],
#         chunks_used=result["chunks_used"],
#         message_id=assistant_message.id
#     )


# @router.get("/topics/{topic_id}/history", response_model=ChatHistoryResponse)
# def get_topic_chat_history(
#     topic_id: int,
#     limit: int = 50,
#     offset: int = 0,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Get chat history for a topic
#     """
#     # Verify topic exists and user has access
#     topic = db.query(Topic).filter(Topic.id == topic_id).first()
#     if not topic:
#         raise HTTPException(status_code=404, detail="Topic not found")
    
#     file = db.query(File).filter(File.id == topic.file_id).first()
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="Access denied")
    
#     # Get messages
#     messages = get_chat_history(
#         db=db,
#         topic_id=topic_id,
#         user_id=current_user.id,
#         limit=limit,
#         offset=offset
#     )
    
#     # Get total count
#     from app.models.chat_message import ChatMessage
#     total = db.query(ChatMessage).filter(
#         ChatMessage.topic_id == topic_id,
#         ChatMessage.user_id == current_user.id
#     ).count()
    
#     return ChatHistoryResponse(
#         messages=messages,
#         total=total,
#         offset=offset,
#         limit=limit
#     )


# @router.delete("/topics/{topic_id}/history", status_code=status.HTTP_204_NO_CONTENT)
# def clear_chat_history(
#     topic_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Clear chat history for a topic
#     """
#     # Verify access
#     topic = db.query(Topic).filter(Topic.id == topic_id).first()
#     if not topic:
#         raise HTTPException(status_code=404, detail="Topic not found")
    
#     file = db.query(File).filter(File.id == topic.file_id).first()
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="Access denied")
    
#     # Delete history
#     success = delete_chat_history(
#         db=db,
#         topic_id=topic_id,
#         user_id=current_user.id
#     )
    
#     if not success:
#         raise HTTPException(status_code=500, detail="Failed to clear history")
    
#     return None


# @router.get("/topics/{topic_id}/stats")
# def get_topic_stats(
#     topic_id: int,
#     db: Session = Depends(get_db),
#     current_user=Depends(get_current_user)
# ):
#     """
#     Get statistics about chat for a topic
#     """
#     # Verify access
#     topic = db.query(Topic).filter(Topic.id == topic_id).first()
#     if not topic:
#         raise HTTPException(status_code=404, detail="Topic not found")
    
#     file = db.query(File).filter(File.id == topic.file_id).first()
#     folder = db.query(Folder).filter(Folder.id == file.folder_id).first()
#     classroom = db.query(Classroom).filter(Classroom.id == folder.classroom_id).first()
    
#     if current_user not in classroom.members:
#         raise HTTPException(status_code=403, detail="Access denied")
    
#     stats = get_chat_statistics(db=db, topic_id=topic_id)
    
#     return {
#         "topic_id": topic_id,
#         "topic_name": topic.topic_name,
#         **stats
#     }