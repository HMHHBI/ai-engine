import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limiter import limiter
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.repositories.user_repo import UserRepository
from app.schemas.user_schema import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)


@router.post("/signup", response_model=UserOut)
@limiter.limit("5/minute")
def signup(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = UserRepository.get_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = UserRepository.create(
        db,
        name=user_data.name,
        email=user_data.email,
        password=user_data.password,
    )
    return new_user


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    user = UserRepository.get_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user_id=user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "name": user.name,
            "email": user.email,
            "plan": user.plan.value if user.plan else "FREE",
        },
    }


@router.post("/google")
@limiter.limit("10/minute")
async def google_auth(request: Request, data: dict, db: Session = Depends(get_db)):
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token missing")

    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
        email = idinfo["email"]
        name = idinfo.get("name", "User")
        picture = idinfo.get("picture")

        user = UserRepository.get_by_email(db, email)
        if not user:
            user = UserRepository.create(
                db,
                name=name,
                email=email,
                password="google_oauth_protected",
                profile_image=picture,
            )

        access_token = create_access_token(user_id=user.id)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "name": user.name,
                "email": user.email,
                "profile_image": user.profile_image,
                "plan": user.plan.value if user.plan else "FREE",
            },
        }
    except Exception:
        logger.exception("Google authentication failed during token verification")
        raise HTTPException(status_code=400, detail="Invalid Google Token")


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request, req: ForgotPasswordRequest, db: Session = Depends(get_db)
):
    user, token = UserRepository.create_reset_token(
        db,
        req.email,
        expires_minutes=30,
    )

    if not user or not token:
        return {"message": "If email is registered, reset link sent."}

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={token}"

    message = MessageSchema(
        subject="Hassan AI - Password Reset",
        recipients=[req.email],
        body=f"Hi {user.name}, reset your password here: {reset_link}",
        subtype=MessageType.html,
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    return {"message": "Reset link sent"}


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(
    request: Request, req: ResetPasswordRequest, db: Session = Depends(get_db)
):
    user = UserRepository.get_by_valid_reset_token(db, req.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    UserRepository.consume_reset_token(db, user, req.new_password)
    return {"message": "Password updated successfully"}
