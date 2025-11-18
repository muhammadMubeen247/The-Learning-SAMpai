from pydantic import BaseModel
from typing import Optional, List

class TopicBase(BaseModel):
    topic_name: str
    introduction: Optional[str] = None
    order: int = 0

class TopicCreate(TopicBase):
    file_id: int

class TopicOut(TopicBase):
    id: int
    file_id: int

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)

class TopicWithStats(TopicOut):
    """Topic with additional statistics"""
    message_count: int = 0  # Number of chat messages
    
    class Config:
        from_attributes = True