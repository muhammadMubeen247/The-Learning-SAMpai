from pydantic import BaseModel
from typing import List, Optional

class FileOut(BaseModel):
    id: int
    filename: str
    file_url: str
    description: Optional[str]

    class Config:
        orm_mode = True

class FolderCreate(BaseModel):
    name: str

class FolderOut(BaseModel):
    id: int
    name: str
    files: List[FileOut] = []

    class Config:
        orm_mode = True
