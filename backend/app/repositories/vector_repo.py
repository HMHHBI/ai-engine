from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import delete, select, update

from app.db.models import Chat, DocumentChunk
from app.db.session import session_scope


class VectorRepository:
    """
    Tenant-scoped repository for document chunks and vector search.
    Security invariant: user_id -> Chat.user_id -> Chat.id -> DocumentChunk.chat_id
    """

    @staticmethod
    def _validate_ids(user_id: int, chat_id: int) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")
        if chat_id <= 0:
            raise ValueError("chat_id must be a positive integer.")

    @staticmethod
    def replace_document_chunks(
        user_id: int,
        chat_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
        pdf_context: str,
    ) -> list[dict[str, Any]]:
        """
        Atomically replace all document chunks owned by a chat.

        The owning chat row is locked for the duration of the transaction
        so concurrent document replacements are serialized.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        if not chunks_with_embeddings:
            raise ValueError("chunks_with_embeddings cannot be empty.")

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
                raise LookupError("Chat not found.")

            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.chat_id == chat_id,
                )
            )

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    chat_id=chat_id,
                    content=chunk.text,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                )
                db.add(db_obj)
                db_objs.append(db_obj)

            if not db_objs:
                raise ValueError(
                    "No valid document chunks with embeddings were provided."
                )

            chat.pdf_context = pdf_context

            db.flush()

            return [
                {
                    "id": chunk.id,
                    "chat_id": chunk.chat_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def store_document_chunks(
        user_id: int,
        chat_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
    ) -> list[dict[str, Any]]:
        VectorRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        if not chunks_with_embeddings:
            return []

        with session_scope() as db:
            chat_exists = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat_exists is None:
                raise LookupError("Chat not found.")

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    chat_id=chat_id,
                    content=chunk.text,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    embedding=embedding,
                )
                db.add(db_obj)
                db_objs.append(db_obj)

            if not db_objs:
                return []

            db.flush()

            return [
                {
                    "id": chunk.id,
                    "chat_id": chunk.chat_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def search_similar_chunks(
        user_id: int,
        chat_id: int,
        query_vector: list[float],
        top_k: int = 6,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:
        VectorRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        if not query_vector:
            return []

        if top_k <= 0 or top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")

        if max_distance < 0 or adaptive_margin < 0:
            raise ValueError("Distance parameters cannot be negative.")

        distance = DocumentChunk.embedding.cosine_distance(query_vector).label(
            "distance"
        )

        with session_scope() as db:
            results = db.execute(
                select(DocumentChunk, distance)
                .join(
                    Chat,
                    Chat.id == DocumentChunk.chat_id,
                )
                .where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                    DocumentChunk.embedding.is_not(None),
                )
                .order_by(distance)
                .limit(top_k)
            ).all()

            if not results:
                return []

            best_distance = float(results[0].distance)

            if best_distance > max_distance:
                return []

            adaptive_limit = min(
                best_distance + adaptive_margin,
                max_distance,
            )

            filtered_results = [
                row for row in results if float(row.distance) <= adaptive_limit
            ]

            return [
                {
                    "id": chunk.id,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "distance": float(distance_value),
                }
                for chunk, distance_value in filtered_results
            ]

    @staticmethod
    def delete_document_chunks(
        user_id: int,
        chat_id: int,
    ) -> bool:
        VectorRepository._validate_ids(
            user_id=user_id,
            chat_id=chat_id,
        )

        with session_scope() as db:
            authorized_chat = db.execute(
                select(Chat.id).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if authorized_chat is None:
                return False

            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.chat_id == chat_id,
                )
            )

            return True
