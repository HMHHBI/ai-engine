from __future__ import annotations

import base64
import logging
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.models import User
from app.db.session import get_db
from app.repositories.user_repo import UserRepository
from app.utils.file_validation import (
    read_upload_with_limit,
    validate_image_bytes,
)

PROFILE_IMAGE_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


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
    try:
        image_base64 = None
        if profile_img and profile_img.filename:
            file_content = await read_upload_with_limit(
                profile_img, max_bytes=PROFILE_IMAGE_MAX_BYTES
            )
            validate_image_bytes(file_content, profile_img.content_type)
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to update profile user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update profile.",
        )
