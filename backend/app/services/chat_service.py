from __future__ import annotations

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
    ):
        """
        Prepare a chat turn while keeping external image uploads outside
        the repository layer.
        """
        images = ChatApplicationService._parse_images(
            image_data_list,
        )

        cloud_urls: list[str] = []

        try:
            for image in images:
                if image.startswith(("http://", "https://")):
                    cloud_urls.append(image)
                    continue

                url = await asyncio.to_thread(
                    upload_image_to_cloud,
                    image,
                    "chat_messages",
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
