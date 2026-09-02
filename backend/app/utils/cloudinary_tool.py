from __future__ import annotations

import logging

import cloudinary
import cloudinary.uploader

from app.core.config import settings

logger = logging.getLogger(__name__)


cloudinary.config(
    cloud_name=settings.CLOUDINARY_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


def upload_image_to_cloud(
    base64_str: str,
    folder: str = "chats",
) -> str | None:
    """
    Upload a base64 image to Cloudinary.

    Returns the secure URL on success and None on failure.
    Sensitive image contents are never logged.
    """
    try:
        result = cloudinary.uploader.upload(
            f"data:image/png;base64,{base64_str}",
            folder=f"hassan_ai/{folder}",
            transformation=[
                {
                    "width": 800,
                    "crop": "limit",
                },
                {
                    "quality": "auto",
                },
            ],
        )

        secure_url = result.get("secure_url")

        if not secure_url:
            logger.warning("Cloudinary upload returned no secure URL.")
            return None

        return str(secure_url)

    except Exception:
        logger.exception("Cloudinary image upload failed.")
        return None
