from pydantic import BaseModel
from typing import Optional

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