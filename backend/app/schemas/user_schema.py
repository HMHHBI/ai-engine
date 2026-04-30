from pydantic import BaseModel, EmailStr
from typing import Optional
from app.db.models import UserPlan

# Base properties (Jo har jagah common hain)
class UserBase(BaseModel):
    email: EmailStr
    name: str

# Signup ke waqt kya chahiye
class UserCreate(UserBase):
    password: str

# Frontend ko wapas kya bhejna hai (Password mita kar)
class UserOut(UserBase):
    id: int
    profile_image: Optional[str] = None
    plan: UserPlan
    image_limit: int
    
    class Config:
        from_attributes = True

# Login ke liye
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Forgot Password ke liye
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str