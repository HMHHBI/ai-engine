from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import delete, select

from app.db.models import Chat, Document, DocumentChunk
from app.db.session import session_scope


class VectorRepository:
    """
    Tenant-scoped repository for document chunks and vector search.

    Ownership invariant:
        user_id
            -> Document.user_id
            -> Document.chat_id
            -> Chat.user_id
            -> DocumentChunk.document_id

    `document_id` is the source of truth for vector ownership.

    `chat_id` is intentionally populated on DocumentChunk for the current
    F3-A transition and remains a legacy compatibility field until the
    later cleanup phase removes it.
    """

    VALID_STATUSES = {"processing", "ready", "failed"}

    @staticmethod
    def _validate_ids(
        user_id: int,
        document_id: int,
    ) -> None:
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer.")

        if document_id <= 0:
            raise ValueError("document_id must be a positive integer.")

    @staticmethod
    def _get_owned_document(
        db,
        *,
        user_id: int,
        document_id: int,
        lock: bool = False,
    ) -> Document | None:
        """
        Resolve a document only when BOTH ownership relationships are valid:

        1. Document.user_id == authenticated user
        2. Document.chat_id belongs to authenticated user

        This deliberately does not trust Document.user_id alone.
        """
        query = (
            select(Document)
            .join(
                Chat,
                Chat.id == Document.chat_id,
            )
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
                Chat.user_id == user_id,
            )
        )

        if lock:
            query = query.with_for_update()

        return db.execute(query).scalar_one_or_none()

    @staticmethod
    def replace_document_chunks(
        user_id: int,
        document_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
        pdf_context: str,
    ) -> list[dict[str, Any]]:
        """
        Atomically replace all chunks belonging to one document.

        Ownership is verified through both:

            Document.user_id == user_id
            Chat.user_id == user_id

        The Document row is locked for the duration of the transaction,
        serializing concurrent replacements of the same document.

        Every new DocumentChunk receives:

            document_id = document.id
            chat_id     = document.chat_id

        `chat_id` is retained only as transitional compatibility.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        if not chunks_with_embeddings:
            raise ValueError("chunks_with_embeddings cannot be empty.")

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
                lock=True,
            )

            if document is None:
                raise LookupError("Document not found.")

            chat_id = document.chat_id

            # Delete ONLY this document's chunks.
            #
            # Never delete by chat_id here because one chat may contain
            # multiple documents after the F3-A migration.
            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id,
                )
            )

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    document_id=document.id,
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

            # Transitional compatibility:
            # keep the legacy Chat.pdf_context populated until the later
            # F3 cleanup removes that field.
            chat = db.execute(
                select(Chat).where(
                    Chat.id == chat_id,
                    Chat.user_id == user_id,
                )
            ).scalar_one_or_none()

            if chat is None:
                raise LookupError("Chat not found.")

            chat.pdf_context = pdf_context

            db.flush()

            return [
                {
                    "id": chunk.id,
                    "chat_id": chunk.chat_id,
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def store_document_chunks(
        user_id: int,
        document_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
    ) -> list[dict[str, Any]]:
        """
        Store chunks for one owned document.

        Every inserted chunk receives both:

            document_id = document.id
            chat_id     = document.chat_id

        Ownership requires BOTH:

            document.user_id == user_id
            document.chat.user_id == user_id
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        if not chunks_with_embeddings:
            return []

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
            )

            if document is None:
                raise LookupError("Document not found.")

            chat_id = document.chat_id

            db_objs: list[DocumentChunk] = []

            for chunk, embedding in chunks_with_embeddings:
                if not embedding:
                    continue

                db_obj = DocumentChunk(
                    document_id=document.id,
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
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in db_objs
            ]

    @staticmethod
    def search_similar_chunks(
        user_id: int,
        document_id: int,
        query_vector: list[float],
        top_k: int = 6,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:
        """
        Search vectors belonging to exactly one owned document.

        The query is constrained by:

            DocumentChunk.document_id == document_id
            Document.user_id == user_id
            Chat.user_id == user_id

        Therefore a document ID from another tenant cannot expose vectors.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
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
                    Document,
                    Document.id == DocumentChunk.document_id,
                )
                .join(
                    Chat,
                    Chat.id == Document.chat_id,
                )
                .where(
                    DocumentChunk.document_id == document_id,
                    Document.user_id == user_id,
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
                    "document_id": chunk.document_id,
                    "chat_id": chunk.chat_id,
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
        document_id: int,
    ) -> bool:
        """
        Delete all chunks belonging to one owned document.

        Deletion is document-scoped, never chat-scoped.
        """
        VectorRepository._validate_ids(
            user_id=user_id,
            document_id=document_id,
        )

        with session_scope() as db:
            document = VectorRepository._get_owned_document(
                db,
                user_id=user_id,
                document_id=document_id,
            )

            if document is None:
                return False

            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document.id,
                )
            )

            return True
