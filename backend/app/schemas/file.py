from pydantic import BaseModel
from typing import Optional

class FileCreate(BaseModel):
    filename: str
    file_url: str
    file_key: str  # Added field for R2 object key
    description: Optional[str] = None

class FileOut(BaseModel):
    id: int
    filename: str
    file_url: str
    description: Optional[str]

    class Config:
        orm_mode = True
