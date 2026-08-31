from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import delete, select, update

from app.db.models import Chat, DocumentChunk
from app.db.session import session_scope


class VectorRepository:
    """
    Repository for document chunks and vector similarity search.

    IMPORTANT:
    Repository methods own their database sessions.

    This allows them to safely execute inside asyncio.to_thread()
    / Starlette threadpool workers without receiving a request-scoped
    SQLAlchemy Session from the async endpoint.
    """

    @staticmethod
    def replace_document_chunks(
        chat_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
        pdf_context: str,
    ) -> list[dict[str, Any]]:
        """
        Atomically replace all document chunks belonging to a chat.

        The entire delete + insert + chat-context update occurs inside
        one transaction.
        """

        if chat_id <= 0:
            raise ValueError("chat_id must be a positive integer.")

        if not chunks_with_embeddings:
            raise ValueError("chunks_with_embeddings cannot be empty.")

        with session_scope() as db:
            # Delete existing chunks for this chat.
            db.execute(delete(DocumentChunk).where(DocumentChunk.chat_id == chat_id))

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

            # Update document context.
            result = db.execute(
                update(Chat).where(Chat.id == chat_id).values(pdf_context=pdf_context)
            )

            if result.rowcount != 1:
                raise ValueError(f"Chat {chat_id} does not exist.")

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
        chat_id: int,
        chunks_with_embeddings: Sequence[tuple[Any, list[float]]],
    ) -> list[dict[str, Any]]:
        """
        Insert document chunks in a single transaction.
        """

        if chat_id <= 0:
            raise ValueError("chat_id must be a positive integer.")

        if not chunks_with_embeddings:
            return []

        with session_scope() as db:
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
        chat_id: int,
        query_vector: list[float],
        top_k: int = 6,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:
        """
        Perform cosine-distance vector search.

        A fresh SQLAlchemy session is created for this operation.
        """

        if chat_id <= 0:
            raise ValueError("chat_id must be a positive integer.")

        if not query_vector:
            return []

        if top_k <= 0:
            raise ValueError("top_k must be greater than zero.")

        if max_distance < 0:
            raise ValueError("max_distance cannot be negative.")

        if adaptive_margin < 0:
            raise ValueError("adaptive_margin cannot be negative.")

        distance = DocumentChunk.embedding.cosine_distance(query_vector).label(
            "distance"
        )

        with session_scope() as db:
            results = db.execute(
                select(
                    DocumentChunk,
                    distance,
                )
                .where(
                    DocumentChunk.chat_id == chat_id,
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
