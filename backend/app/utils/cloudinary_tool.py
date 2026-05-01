import cloudinary
import cloudinary.uploader
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

def upload_image_to_cloud(base64_str: str, folder: str = "chats"):
    try:
        # Base64 ko direct upload karta hai
        result = cloudinary.uploader.upload(
            f"data:image/png;base64,{base64_str}",
            folder=f"hassan_ai/{folder}",
            transformation=[
                {"width": 800, "crop": "limit"}, # Auto compress
                {"quality": "auto"}
            ]
        )
        return result['secure_url']
    except Exception as e:
        print(f"Cloudinary Error: {e}")
        return None