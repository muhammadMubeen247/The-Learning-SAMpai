from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.schemas.topic import TopicOut

class FileBase(BaseModel):
    filename: str
    description: Optional[str] = None

class FileCreate(FileBase):
    folder_id: int

class FileOut(FileBase):
    id: int
    file_url: str
    file_key: str
    file_type: Optional[str]
    file_size: Optional[int]
    processing_status: str
    folder_id: int
    uploaded_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class FileWithTopics(FileOut):
    """File with embedded topics"""
    topics: List[TopicOut] = []

    class Config:
        from_attributes = True