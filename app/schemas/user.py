from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None

class User(UserBase):
    id: int
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True 