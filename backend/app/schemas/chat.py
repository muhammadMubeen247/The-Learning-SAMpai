from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any


class QuestionRequest(BaseModel):
    """Request to ask a question"""
    question: str
    file_id: Optional[int] = None  # Optional: limit to specific file


class SourceInfo(BaseModel):
    """Information about a source chunk"""
    file_id: int
    page_number: Optional[int]
    slide_number: Optional[int]
    content_preview: str


class QuestionResponse(BaseModel):
    """Response to a question"""
    answer: str
    sources: List[SourceInfo]
    confidence: str
    chunks_used: int
    message_id: int  # ID of saved message


class ChatMessageOut(BaseModel):
    """Chat message output"""
    id: int
    topic_id: int
    user_id: int
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[str] = None

    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """Chat history response with pagination"""
    messages: List[ChatMessageOut]
    total: int
    offset: int
    limit: int