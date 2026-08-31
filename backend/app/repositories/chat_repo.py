from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import delete, select, update

from app.core.config import settings
from app.db.models import AILog, Chat, Message
from app.db.session import session_scope
from app.utils.cloudinary_tool import upload_image_to_cloud


class ChatRepository:
    """
    Database repository for chats and messages.

    Repository methods own their database sessions. This prevents
    request-scoped SQLAlchemy sessions from being passed into async
    threadpool execution.
    """

    @staticmethod
    def get_by_id(
        chat_id: int,
        user_id: int,
    ) -> Optional[Chat]:
        with session_scope() as db:
            return db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

    @staticmethod
    def get_all_by_user(
        user_id: int,
    ) -> list[Chat]:
        with session_scope() as db:
            return list(
                db.execute(
                    select(Chat).where(Chat.user_id == user_id).order_by(Chat.id.desc())
                ).scalars()
            )

    @staticmethod
    def create_chat(
        user_id: int,
        title: str = "New Chat",
    ) -> Chat:
        with session_scope() as db:
            new_chat = Chat(
                user_id=user_id,
                title=title,
                ai_provider=settings.DEFAULT_AI_PROVIDER.value,
                ai_model=settings.DEFAULT_AI_MODEL.value,
                embedding_provider=(settings.DEFAULT_EMBEDDING_PROVIDER.value),
            )

            db.add(new_chat)
            db.flush()

            return new_chat

    @staticmethod
    def update_title(
        chat_id: int,
        new_title: str,
    ) -> Optional[Chat]:
        title = new_title.strip()

        if not title:
            raise ValueError("Chat title cannot be empty.")

        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(Chat.id == chat_id)
            ).scalar_one_or_none()

            if chat is None:
                return None

            chat.title = title
            db.flush()

            return chat

    @staticmethod
    def delete_chat(
        chat_id: int,
        user_id: int,
    ) -> bool:
        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat is None:
                return False

            db.delete(chat)

            return True

    @staticmethod
    def add_message(
        chat_id: int,
        role: str,
        content: str,
        image_data_list: Optional[list[str] | str] = None,
    ) -> Message:
        normalized_role = role.strip().lower()

        if normalized_role not in {"user", "ai", "assistant"}:
            raise ValueError(
                "Invalid message role. " "Expected 'user', 'ai', or 'assistant'."
            )

        if not content.strip():
            raise ValueError("Message content cannot be empty.")

        cloud_urls: list[str] = []

        if image_data_list:
            if isinstance(image_data_list, str):
                try:
                    images = json.loads(image_data_list)
                except json.JSONDecodeError as exc:
                    raise ValueError("image_data_list contains invalid JSON.") from exc
            else:
                images = image_data_list

            if not isinstance(images, list):
                raise ValueError("image_data_list must be a list.")

            for image in images:
                image_value = str(image)

                if image_value.startswith("http://") or image_value.startswith(
                    "https://"
                ):
                    cloud_urls.append(image_value)
                    continue

                url = upload_image_to_cloud(
                    image_value,
                    folder="chat_messages",
                )

                if url:
                    cloud_urls.append(url)

        db_image_data = json.dumps(cloud_urls) if cloud_urls else None

        with session_scope() as db:
            # Verify chat exists before inserting the message.
            chat_exists = db.execute(
                select(Chat.id).where(Chat.id == chat_id)
            ).scalar_one_or_none()

            if chat_exists is None:
                raise ValueError(f"Chat {chat_id} does not exist.")

            new_message = Message(
                chat_id=chat_id,
                role=normalized_role,
                content=content,
                image_data=db_image_data,
            )

            db.add(new_message)
            db.flush()

            return new_message

    @staticmethod
    def update_pdf_context(
        chat_id: int,
        text: str,
    ) -> Optional[Chat]:
        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(Chat.id == chat_id)
            ).scalar_one_or_none()

            if chat is None:
                return None

            chat.pdf_context = text
            db.flush()

            return chat

    @staticmethod
    def save_ai_log(
        task: str,
        prompt: str,
        response: str,
        user_id: Optional[int] = None,
    ) -> AILog:
        with session_scope() as db:
            log = AILog(
                user_id=user_id,
                task=task,
                prompt=prompt,
                response=response,
            )

            db.add(log)
            db.flush()

            return log

    @staticmethod
    def get_history(
        chat_id: int,
        limit: int = 10,
    ) -> list[Message]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        with session_scope() as db:
            messages = list(
                db.execute(
                    select(Message)
                    .where(Message.chat_id == chat_id)
                    .order_by(Message.id.desc())
                    .limit(limit)
                ).scalars()
            )

            messages.reverse()

            return messages

    @staticmethod
    def delete_messages_after(
        chat_id: int,
        user_id: int,
        after_index: int,
    ) -> bool:
        """
        Delete messages from a given zero-based message index onward.

        user_id is verified through the chat ownership check.
        """

        if after_index < 0:
            raise ValueError("after_index cannot be negative.")

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                return False

            messages = list(
                db.execute(
                    select(Message.id)
                    .where(Message.chat_id == chat_id)
                    .order_by(Message.id.asc())
                ).scalars()
            )

            if after_index >= len(messages):
                return True

            target_message_id = messages[after_index]

            db.execute(
                delete(Message).where(
                    Message.chat_id == chat_id,
                    Message.id >= target_message_id,
                )
            )

            return True
