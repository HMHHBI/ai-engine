from sqlalchemy.orm import Session
from app.db.models import User
from app.core.security import hash_password
from app.utils.cloudinary_tool import upload_image_to_cloud

class UserRepository:
    @staticmethod
    def get_by_email(db: Session, email: str):
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_by_id(db: Session, user_id: int):
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_reset_token(db: Session, token: str):
        return db.query(User).filter(User.reset_token == token).first()

    @staticmethod
    def create(db: Session, name: str, email: str, password: str, profile_image=None, plan="FREE"):
        hashed_pwd = hash_password(password)
        new_user = User(
            name=name, email=email, password=hashed_pwd, 
            profile_image=profile_image, plan=plan
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def update_profile(db: Session, user_id: int, name: str = None, image_base64: str = None):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            if name: user.name = name
            if image_base64:
                # 1. Cloudinary par upload karo
                cloud_url = upload_image_to_cloud(image_base64, folder="profiles")
                # 2. Database mein URL save karo
                if cloud_url:
                    user.profile_image = cloud_url
            db.commit()
        return user

    @staticmethod
    def set_reset_token(db: Session, email: str, token: str):
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.reset_token = token
            db.commit()
        return user
    
    @staticmethod
    def upgrade_to_pro(db: Session, user_id: int):
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = "PRO"
            # PRO bante hi limits bhi barha dein (Professional Touch)
            user.image_limit = 1000 
            user.search_limit = 5000
            db.commit()
            db.refresh(user)
        return user