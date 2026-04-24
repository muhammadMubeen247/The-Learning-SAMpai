from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ChatMessageBase(BaseModel):
    content: str

class ChatMessageCreate(ChatMessageBase):
    file_id: int

class ChatMessageOut(ChatMessageBase):
    id: int
    file_id: int
    user_id: int
    role: str
    timestamp: datetime
    metadata: Optional[str] = None

    class Config:
        from_attributes = True
