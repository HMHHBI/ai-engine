import base64
import os
import shutil
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.models import User
from app.db.session import get_db
from app.repositories.user_repo import UserRepository

router = APIRouter(prefix="/user", tags=["user"])
UPLOAD_DIR = "static/profiles"


@router.get("/me")
@limiter.limit("30/minute")
def get_my_profile(request: Request, current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.name,
        "email": current_user.email,
        "profile_image": current_user.profile_image or "/default-avatar.png",
        "plan": current_user.plan.value if current_user.plan else "FREE",
        "limits": {
            "image": current_user.image_limit,
            "search": current_user.search_limit,
        },
    }


@router.put("/update-profile")
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    name: str = Form(None),
    profile_img: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    image_base64 = None
    if profile_img:
        file_content = await profile_img.read()
        image_base64 = base64.b64encode(file_content).decode("utf-8")

    updated_user = UserRepository.update_profile(
        db, current_user.id, name=name, image_base64=image_base64
    )
    return {
        "message": "Profile updated",
        "user": {
            "name": updated_user.name,
            "image": updated_user.profile_image,
        },
    }


@router.post("/upgrade-plan")
@limiter.limit("5/minute")
async def upgrade_plan(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        updated_user = UserRepository.upgrade_to_pro(db, current_user.id)

        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "success": True,
            "message": "Welcome to PRO, Hassan! 🚀",
            "plan": updated_user.plan,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Upgrade failed internally")