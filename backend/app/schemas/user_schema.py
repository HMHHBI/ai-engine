from datetime import datetime
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


class UserProfileOut(BaseModel):
    id: int
    name: Optional[str] = None
    full_name: str
    email: EmailStr
    picture: Optional[str] = None
    profile_image: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    plan: UserPlan
    image_limit: int
    limits: dict[str, int]

    class Config:
        from_attributes = True

class UsageMetricOut(BaseModel):
    remaining: int

class UserUsageOut(BaseModel):
    plan: UserPlan
    image: UsageMetricOut
    search: UsageMetricOut

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