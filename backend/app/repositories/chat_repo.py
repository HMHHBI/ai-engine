from __future__ import annotations

import json
import re
from typing import Any, Optional, TypedDict

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.db.models import AILog, Chat, Document, Message
from app.db.session import session_scope

SOURCE_SNIPPET_MAX_CHARS = 800


class RetrievedSource(TypedDict):
    id: int
    document_id: int | None
    page_number: int | None
    chunk_index: int | None
    distance: float
    snippet: str | None


def normalize_source_snippet(value: Any) -> str | None:
    if value is None:
        return None

    normalized = re.sub(r"\s+", " ", str(value)).strip()

    if not normalized:
        return None

    if len(normalized) <= SOURCE_SNIPPET_MAX_CHARS:
        return normalized

    return normalized[: SOURCE_SNIPPET_MAX_CHARS - 1].rstrip() + "…"


def _normalize_sources(raw_sources: Any) -> Optional[list[dict[str, Any]]]:
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
            doc_id = (
                int(item["document_id"])
                if item.get("document_id") is not None
                else None
            )
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
                    "document_id": doc_id,
                    "page_number": page_num,
                    "chunk_index": chunk_idx,
                    "distance": round(distance, 6),
                    "snippet": normalize_source_snippet(item.get("snippet")),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    return normalized if normalized else None


class ChatRepository:
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
    def _session_query(
        user_id: int,
        chat_id: int | None = None,
    ):
        document_count = (
            select(func.count(Document.id))
            .where(
                Document.chat_id == Chat.id,
                Document.user_id == user_id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        primary_document_title = (
            select(Document.filename)
            .where(
                Document.chat_id == Chat.id,
                Document.user_id == user_id,
                Document.status == "ready",
            )
            .order_by(
                Document.updated_at.desc(),
                Document.id.desc(),
            )
            .limit(1)
            .correlate(Chat)
            .scalar_subquery()
        )

        latest_document_updated_at = (
            select(func.max(Document.updated_at))
            .where(
                Document.chat_id == Chat.id,
                Document.user_id == user_id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        message_count = (
            select(func.count(Message.id))
            .where(
                Message.chat_id == Chat.id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        latest_message_created_at = (
            select(func.max(Message.created_at))
            .where(
                Message.chat_id == Chat.id,
            )
            .correlate(Chat)
            .scalar_subquery()
        )

        query = select(
            Chat,
            document_count.label("attached_documents_count"),
            primary_document_title.label("primary_document_title"),
            message_count.label("message_count"),
            latest_message_created_at.label("latest_message_created_at"),
            latest_document_updated_at.label("latest_document_updated_at"),
        ).where(
            Chat.user_id == user_id,
        )

        if chat_id is not None:
            query = query.where(Chat.id == chat_id)

        return query

    @staticmethod
    def _session_metadata_from_row(
        row: Any,
    ) -> dict[str, Any]:
        chat = row[0]

        timestamps = [
            timestamp
            for timestamp in (
                row.latest_message_created_at,
                row.latest_document_updated_at,
            )
            if timestamp is not None
        ]

        return {
            "id": chat.id,
            "user_id": chat.user_id,
            "title": chat.title,
            "created_at": getattr(chat, "created_at", None) or datetime.now(timezone.utc),
            "updated_at": getattr(chat, "updated_at", None) or datetime.now(timezone.utc),
            "pdf_context": chat.pdf_context,
            "ai_provider": chat.ai_provider,
            "ai_model": chat.ai_model,
            "embedding_provider": chat.embedding_provider,
            "persona": chat.persona,
            "custom_instructions": chat.custom_instructions,
            "attached_documents_count": int(row.attached_documents_count or 0),
            "primary_document_title": row.primary_document_title,
            "message_count": int(row.message_count or 0),
            "last_active_at": max(timestamps) if timestamps else None,
        }

    @staticmethod
    def get_all_by_user(
        user_id: int,
    ) -> list[dict[str, Any]]:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")

        with session_scope() as db:
            rows = db.execute(
                ChatRepository._session_query(user_id).order_by(Chat.id.desc())
            ).all()

            sessions = [ChatRepository._session_metadata_from_row(row) for row in rows]

            sessions.sort(
                key=lambda session: (
                    session["last_active_at"] is not None,
                    session["last_active_at"],
                    session["id"],
                ),
                reverse=True,
            )

            return sessions

    @staticmethod
    def get_session_metadata(
        chat_id: int,
        user_id: int,
    ) -> Optional[dict[str, Any]]:
        if chat_id <= 0 or user_id <= 0:
            raise ValueError("chat_id and user_id must be positive integers.")

        with session_scope() as db:
            row = db.execute(
                ChatRepository._session_query(
                    user_id=user_id,
                    chat_id=chat_id,
                )
            ).first()

            if row is None:
                return None

            return ChatRepository._session_metadata_from_row(row)

    @staticmethod
    def _is_generic_title(title: Any) -> bool:
        if not isinstance(title, str):
            return False
        normalized = (title or "").strip().lower()

        if not normalized:
            return True

        if normalized in {
            "new chat",
            "new research",
            "untitled chat",
            "untitled research",
        }:
            return True

        return bool(
            re.fullmatch(
                r"chat\s*#\s*\d+",
                normalized,
            )
        )

    @staticmethod
    def _clean_document_filename(
        filename: str,
    ) -> str:
        cleaned = re.sub(
            r"\.[^.]+$",
            "",
            filename.strip(),
        )
        cleaned = re.sub(
            r"[_-]+",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"\s+",
            " ",
            cleaned,
        ).strip()

        if not cleaned:
            return ""

        return cleaned[:1].upper() + cleaned[1:]

    @staticmethod
    def _clean_research_title(
        value: str,
    ) -> str:
        cleaned = re.sub(
            r"\s+",
            " ",
            value.strip(),
        )
        cleaned = re.sub(
            r"^[\s\-:]+|[\s\-:?!]+$",
            "",
            cleaned,
        )

        if not cleaned:
            return ""

        if len(cleaned) > 80:
            cleaned = f"{cleaned[:77].rstrip()}..."

        return cleaned[:1].upper() + cleaned[1:]

    @staticmethod
    def infer_and_set_title_from_document(
        chat_id: int,
        user_id: int,
        filename: str,
    ) -> Optional[str]:
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

            if not ChatRepository._is_generic_title(chat.title):
                return chat.title

            title = ChatRepository._clean_document_filename(filename)

            if title:
                chat.title = title
                db.flush()

            return chat.title

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

                normalized_image_urls.append(image_value)

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

            if ChatRepository._is_generic_title(chat.title):
                document_filename = db.execute(
                    select(Document.filename)
                    .where(
                        Document.chat_id == chat.id,
                        Document.user_id == user_id,
                    )
                    .order_by(
                        Document.updated_at.desc(),
                        Document.id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()

                document_title = (
                    ChatRepository._clean_document_filename(document_filename)
                    if document_filename
                    else ""
                )

                explicit_title = (
                    ChatRepository._clean_research_title(title) if title else ""
                )

                if document_title:
                    chat.title = document_title
                elif explicit_title:
                    chat.title = explicit_title
                else:
                    chat.title = (
                        ChatRepository._clean_research_title(normalized_content)
                        or "New Research"
                    )

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
        normalized_role = role.strip().lower()

        if normalized_role not in {
            "user",
            "ai",
            "assistant",
        }:
            raise ValueError(
                "Invalid message role. Expected 'user', 'ai', or 'assistant'."
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

            db_image_data = json.dumps(normalized_images)

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
