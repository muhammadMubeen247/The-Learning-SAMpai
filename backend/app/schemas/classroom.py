from pydantic import BaseModel
from typing import Optional, List

class UserOut(BaseModel):
    id: int
    username: str
    email: str
    class Config:
        orm_mode = True

class ClassroomCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ClassroomOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    code: str
    owner_id: int
    members: List[UserOut] = []

    class Config:
        orm_mode = True
