from __future__ import annotations
import base64

import asyncio
import json
import logging
from typing import Optional

from app.repositories.chat_repo import ChatRepository
from app.utils.cloudinary_tool import upload_image_to_cloud

logger = logging.getLogger(__name__)


class ChatApplicationService:
    """
    Application-layer orchestration for chat mutations.

    External side effects such as Cloudinary uploads are handled here,
    while database persistence remains inside ChatRepository.
    """

    @staticmethod
    def _parse_images(
        image_data_list: Optional[list[str] | str],
    ) -> list[str]:
        if not image_data_list:
            return []

        if isinstance(image_data_list, str):
            try:
                images = json.loads(image_data_list)
            except json.JSONDecodeError as exc:
                raise ValueError("image_data_list contains invalid JSON.") from exc
        else:
            images = image_data_list

        if not isinstance(images, list):
            raise ValueError("image_data_list must be a list.")

        return [str(image).strip() for image in images if str(image).strip()]

    @staticmethod
    async def prepare_chat_turn(
        *,
        chat_id: int,
        user_id: int,
        content: str,
        new_title: Optional[str] = None,
        image_data_list: Optional[list[str] | str] = None,
        image_mime_list: Optional[list[str] | str] = None,
    ):
        """
        Prepare a chat turn while keeping external image uploads outside
        the repository layer.
        """
        images = ChatApplicationService._parse_images(
            image_data_list,
        )
        mimes = ChatApplicationService._parse_images(
            image_mime_list,
        ) if image_mime_list is not None else []

        if image_data_list is not None and not images:
            raise ValueError("Decoded image content cannot be empty.")

        # Phase 1: Validate ALL images before executing any uploads
        verified_uploads: list[tuple[str, str]] = []
        passthrough_urls: list[tuple[int, str]] = []

        for idx, image in enumerate(images):
            if image.startswith(("http://", "https://")):
                passthrough_urls.append((idx, image))
                continue

            declared_mime = mimes[idx] if idx < len(mimes) else None
            if not declared_mime:
                raise ValueError("Chat image is missing declared MIME type.")

            normalized_mime = declared_mime.lower().split(";", 1)[0].strip()
            allowed_mimes = {"image/jpeg", "image/png", "image/webp"}
            if normalized_mime not in allowed_mimes:
                raise ValueError(f"Unsupported image format: {declared_mime}. Allowed formats: image/jpeg, image/png, image/webp.")

            try:
                raw_bytes = base64.b64decode(image, validate=True)
            except Exception as exc:
                raise ValueError("Invalid image base64 data.") from exc

            if not raw_bytes:
                raise ValueError("Decoded image content cannot be empty.")

            is_png = raw_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            is_jpeg = raw_bytes.startswith(b"\xff\xd8\xff")
            is_webp = len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP"

            detected_mime = None
            if is_png:
                detected_mime = "image/png"
            elif is_jpeg:
                detected_mime = "image/jpeg"
            elif is_webp:
                detected_mime = "image/webp"

            if detected_mime is None or detected_mime != normalized_mime:
                raise ValueError("Image content does not match its declared type.")

            verified_uploads.append((image, detected_mime))

        # Phase 2: Upload all verified images atomically (no partial/orphaned uploads on validation error)
        cloud_urls: list[str] = []
        try:
            upload_iter = iter(verified_uploads)
            passthrough_dict = dict(passthrough_urls)

            for idx in range(len(images)):
                if idx in passthrough_dict:
                    cloud_urls.append(passthrough_dict[idx])
                else:
                    raw_b64, v_mime = next(upload_iter)
                    url = await asyncio.to_thread(
                        upload_image_to_cloud,
                        raw_b64,
                        "chat_messages",
                        v_mime,
                    )
                    if not url:
                        raise ValueError("Failed to upload chat image.")
                    cloud_urls.append(url)

            return await asyncio.to_thread(
                ChatRepository.prepare_chat_turn,
                chat_id=chat_id,
                user_id=user_id,
                content=content,
                new_title=new_title,
                image_urls=cloud_urls,
            )

        except asyncio.CancelledError:
            logger.info(
                "Chat turn preparation cancelled " "chat_id=%s user_id=%s",
                chat_id,
                user_id,
            )
            raise

        except Exception:
            logger.exception(
                "Chat turn preparation failed " "chat_id=%s user_id=%s",
                chat_id,
                user_id,
            )
            raise
