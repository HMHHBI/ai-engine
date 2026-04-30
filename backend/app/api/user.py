from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import shutil, os

from app.db.session import get_db
from app.api.deps import get_current_user
from app.db.models import User
from app.repositories.user_repo import UserRepository

router = APIRouter(prefix="/user", tags=["user"])
UPLOAD_DIR = "static/profiles"

@router.get("/me")
def get_my_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.name,
        "email": current_user.email,
        "profile_image": current_user.profile_image or "/default-avatar.png",
        "plan": current_user.plan.value if current_user.plan else "FREE",
        "limits": {"image": current_user.image_limit, "search": current_user.search_limit}
    }

@router.put("/update-profile")
async def update_profile(
    name: str = Form(None),
    profile_img: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    image_url = None
    if profile_img:
        file_ext = profile_img.filename.split(".")[-1]
        file_name = f"user_{current_user.id}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_img.file, buffer)
        image_url = f"http://127.0.0.1:8000/static/profiles/{file_name}"

    updated_user = UserRepository.update_profile(db, current_user.id, name=name, image_url=image_url)
    return {"message": "Profile updated", "user": {"name": updated_user.name, "image": updated_user.profile_image}}

@router.post("/upgrade-plan")
async def upgrade_plan(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    try:
        # Ab hum Repository use kar rahe hain
        updated_user = UserRepository.upgrade_to_pro(db, current_user.id)
        
        if not updated_user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "success": True, 
            "message": "Welcome to PRO, Hassan! 🚀", 
            "plan": updated_user.plan
        }
    except Exception as e:
        # Repository mein commit fail ho sakta hai, isliye try-except yahan zaroori hai
        raise HTTPException(status_code=500, detail="Upgrade failed internally")