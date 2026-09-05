from __future__ import annotations

import json
from typing import Any, Optional, TypedDict

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models import AILog, Chat, Message
from app.db.session import session_scope


class RetrievedSource(TypedDict):
    id: int
    page_number: int | None
    chunk_index: int | None
    distance: float


def _normalize_sources(raw_sources: Any) -> Optional[list[dict[str, Any]]]:
    """Validate and normalize source citation metadata before persistence."""
    if not raw_sources:
        return None

    if not isinstance(raw_sources, list):
        return None

    normalized: list[dict[str, Any]] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        try:
            source_id = int(item["id"])
            page_num = (
                int(item["page_number"])
                if item.get("page_number") is not None
                else None
            )
            chunk_idx = (
                int(item["chunk_index"])
                if item.get("chunk_index") is not None
                else None
            )
            distance = (
                float(item["distance"]) if item.get("distance") is not None else 0.0
            )
            normalized.append(
                {
                    "id": source_id,
                    "page_number": page_num,
                    "chunk_index": chunk_idx,
                    "distance": round(distance, 6),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return normalized if normalized else None


class ChatRepository:
    """
    Database repository for chats and messages.

    Repository methods own their database sessions. This prevents
    request-scoped SQLAlchemy sessions from being passed into async
    threadpool execution.

    External side effects such as Cloudinary uploads are intentionally
    handled by the application/service layer.
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
        persona: str = "default",
        custom_instructions: Optional[str] = None,
    ) -> Chat:
        normalized_persona = (
            persona.strip().lower() if persona else "default"
        ) or "default"
        normalized_instructions = (
            custom_instructions.strip()
            if custom_instructions and custom_instructions.strip()
            else None
        )

        with session_scope() as db:
            new_chat = Chat(
                user_id=user_id,
                title=title,
                persona=normalized_persona,
                custom_instructions=normalized_instructions,
                ai_provider=settings.DEFAULT_AI_PROVIDER.value,
                ai_model=settings.DEFAULT_AI_MODEL.value,
                embedding_provider=settings.DEFAULT_EMBEDDING_PROVIDER.value,
            )

            db.add(new_chat)
            db.flush()

            return new_chat

    @staticmethod
    def update_title(
        chat_id: int,
        user_id: int,
        new_title: str,
    ) -> Optional[Chat]:
        title = new_title.strip()

        if not title:
            raise ValueError("Chat title cannot be empty.")

        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat is None:
                return None

            chat.title = title
            db.flush()

            return chat

    @staticmethod
    def update_persona_and_instructions(
        chat_id: int,
        user_id: int,
        persona: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> Optional[Chat]:
        """
        Update chat persona and/or custom instructions with chat ownership verification.
        """
        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat is None:
                return None

            if persona is not None:
                norm_persona = persona.strip().lower()
                chat.persona = norm_persona if norm_persona else "default"

            if custom_instructions is not None:
                norm_instructions = custom_instructions.strip()
                chat.custom_instructions = (
                    norm_instructions if norm_instructions else None
                )

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
    def prepare_chat_turn(
        chat_id: int,
        user_id: int,
        content: str,
        new_title: Optional[str] = None,
        image_urls: Optional[list[str] | str] = None,
    ) -> Optional[Message]:
        """
        Atomically prepare a new chat turn.

        The transaction verifies chat ownership, locks the chat row,
        conditionally initializes the title, and inserts the user
        message.

        External image uploads must already have been completed by
        the application layer. This repository only persists the
        resulting URLs.
        """
        normalized_content = content.strip()

        if not normalized_content:
            raise ValueError("Message content cannot be empty.")

        title: Optional[str] = None

        if new_title is not None:
            title = new_title.strip()

            if not title:
                raise ValueError("Chat title cannot be empty.")

        normalized_image_urls: list[str] = []

        if image_urls:
            if isinstance(image_urls, str):
                try:
                    images = json.loads(image_urls)
                except json.JSONDecodeError as exc:
                    raise ValueError("image_urls contains invalid JSON.") from exc
            else:
                images = image_urls

            if not isinstance(images, list):
                raise ValueError("image_urls must be a list.")

            for image in images:
                image_value = str(image).strip()

                if not image_value.startswith(("http://", "https://")):
                    raise ValueError("image_urls must contain absolute URLs only.")

                normalized_image_urls.append(
                    image_value,
                )

        db_image_data = (
            json.dumps(normalized_image_urls) if normalized_image_urls else None
        )

        with session_scope() as db:
            chat = db.execute(
                select(Chat)
                .where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if chat is None:
                return None

            if title is not None and chat.title == "New Chat":
                chat.title = title

            new_message = Message(
                chat_id=chat.id,
                role="user",
                content=normalized_content,
                image_data=db_image_data,
            )

            db.add(new_message)
            db.flush()

            return new_message

    @staticmethod
    def add_message(
        chat_id: int,
        user_id: int,
        role: str,
        content: str,
        image_data_list: Optional[list[str] | str] = None,
        sources: Optional[list[dict]] = None,
    ) -> Optional[Message]:
        """
        Insert a message only when the authenticated user owns the chat.
        Optionally persists structured RAG source citations (JSONB).
        """
        normalized_role = role.strip().lower()

        if normalized_role not in {
            "user",
            "ai",
            "assistant",
        }:
            raise ValueError(
                "Invalid message role. " "Expected 'user', 'ai', or 'assistant'."
            )

        if not content.strip():
            raise ValueError("Message content cannot be empty.")

        db_image_data = None

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

            normalized_images = [str(image).strip() for image in images]

            if any(
                not image.startswith(("http://", "https://"))
                for image in normalized_images
            ):
                raise ValueError("image_data_list must contain URLs only.")

            db_image_data = json.dumps(
                normalized_images,
            )

        db_sources = _normalize_sources(sources)

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                return None

            new_message = Message(
                chat_id=chat_id,
                role=normalized_role,
                content=content,
                image_data=db_image_data,
                sources=db_sources,
            )

            db.add(new_message)
            db.flush()

            return new_message

    @staticmethod
    def update_pdf_context(
        chat_id: int,
        user_id: int,
        text: str,
    ) -> Optional[Chat]:
        with session_scope() as db:
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
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
        user_id: int,
        limit: int = 10,
    ) -> list[Message]:
        """
        Retrieve message history only for a chat owned by user_id.
        """
        if limit <= 0:
            raise ValueError("limit must be greater than zero.")

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                return []

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
