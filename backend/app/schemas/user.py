from pydantic import BaseModel, EmailStr, Field, validator
import re

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)

    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_-]+$", v):
            raise ValueError('username must contain only letters, numbers, underscores, and hyphens')
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v.encode('utf-8')) > 72:
            raise ValueError('password must be less than 72 bytes when encoded in utf-8')
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d@$!%*#?&]{8,}$", v):
            raise ValueError('password must contain at least one letter and one number')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool = True
    is_verified: bool = False

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    
    @validator('username')
    def validate_username(cls, v):
        if v and not re.match("^[a-zA-Z0-9_-]+$", v):
            raise ValueError('username must contain only letters, numbers, underscores, and hyphens')
        return v