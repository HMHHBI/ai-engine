from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi_mail import FastMail, MessageSchema, MessageType, ConnectionConfig
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import secrets, os

from app.db.session import get_db
from app.schemas.user_schema import UserCreate, UserLogin, UserOut, ForgotPasswordRequest, ResetPasswordRequest
from app.repositories.user_repo import UserRepository
from app.core.security import create_access_token, verify_password, hash_password
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# Email Configuration (Purani logic naye settings ke sath)
conf = ConnectionConfig(
    MAIL_USERNAME = settings.MAIL_USERNAME,
    MAIL_PASSWORD = settings.MAIL_PASSWORD,
    MAIL_FROM = settings.MAIL_FROM,
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True
)

@router.post("/signup", response_model=UserOut)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    # 1. Check if user already exists
    existing_user = UserRepository.get_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 2. Create user via Repository
    new_user = UserRepository.create(
        db, 
        name=user_data.name, 
        email=user_data.email, 
        password=user_data.password
    )
    return new_user

@router.post("/login")
def login(data: UserLogin, db: Session = Depends(get_db)):
    # 1. Get user by email
    user = UserRepository.get_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # 2. Generate JWT Token
    access_token = create_access_token(user_id=user.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "name": user.name,
            "email": user.email,
            "plan": user.plan.value if user.plan else "FREE"
        }
    }
    
@router.post("/google")
async def google_auth(data: dict, db: Session = Depends(get_db)):
    token = data.get("token")
    if not token: raise HTTPException(status_code=400, detail="Token missing")

    try:
        # Google Token Verification
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
        email, name, picture = idinfo['email'], idinfo.get('name', 'User'), idinfo.get('picture')

        user = UserRepository.get_by_email(db, email)
        if not user:
            # Naya user banayein agar mojud nahi
            user = UserRepository.create(db, name=name, email=email, password="google_oauth_protected", profile_image=picture)

        access_token = create_access_token(user_id=user.id)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {"name": user.name, "email": user.email, "profile_image": user.profile_image, "plan": user.plan.value if user.plan else "FREE"}
        }
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Google Token")

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = UserRepository.get_by_email(db, req.email)
    if not user: return {"message": "If email is registered, reset link sent."}

    token = secrets.token_urlsafe(32)
    UserRepository.set_reset_token(db, req.email, token)

    message = MessageSchema(
        subject="Hassan AI - Password Reset",
        recipients=[req.email],
        body=f"Hi {user.name}, reset your password here: http://localhost:5173/reset-password?token={token}",
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    return {"message": "Reset link sent"}

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = UserRepository.get_by_reset_token(db, req.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    # Update password and clear token via Repository logic or direct update
    user.password = hash_password(req.new_password)
    user.reset_token = None
    db.commit()
    
    return {"message": "Password updated successfully"}