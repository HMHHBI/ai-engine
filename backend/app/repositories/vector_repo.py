from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Chat, DocumentChunk


class VectorRepository:

    @staticmethod
    def replace_document_chunks(
        db: Session,
        chat_id: int,
        chunks_with_embeddings: list[tuple[object, list[float]]],
        pdf_context: str,
    ) -> list[DocumentChunk]:
        db.query(DocumentChunk).filter(DocumentChunk.chat_id == chat_id).delete(
            synchronize_session=False
        )

        db_objs = [
            DocumentChunk(
                chat_id=chat_id,
                content=chunk.text,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                embedding=embedding,
            )
            for chunk, embedding in chunks_with_embeddings
        ]
        db.add_all(db_objs)
        db.query(Chat).filter(Chat.id == chat_id).update(
            {Chat.pdf_context: pdf_context}, synchronize_session=False
        )
        db.commit()

        for obj in db_objs:
            db.refresh(obj)

        return db_objs

    @staticmethod
    def store_document_chunks(
        db: Session,
        chat_id: int,
        chunks_with_embeddings: list[tuple[object, list[float]]],
    ) -> list[DocumentChunk]:

        db_objs = [
            DocumentChunk(
                chat_id=chat_id,
                content=chunk.text,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                embedding=embedding,
            )
            for chunk, embedding in chunks_with_embeddings
        ]

        db.add_all(db_objs)
        db.commit()

        for obj in db_objs:
            db.refresh(obj)

        return db_objs

    @staticmethod
    def search_similar_chunks(
        db: Session,
        chat_id: int,
        query_vector: list[float],
        top_k: int = 6,
        max_distance: float = 0.70,
        adaptive_margin: float = 0.15,
    ) -> list[dict[str, Any]]:

        distance = DocumentChunk.embedding.cosine_distance(query_vector).label(
            "distance"
        )

        results = (
            db.query(
                DocumentChunk,
                distance,
            )
            .filter(
                DocumentChunk.chat_id == chat_id,
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(distance)
            .limit(top_k)
            .all()
        )

        if not results:
            return []

        best_distance = float(results[0][1])

        if best_distance > max_distance:
            return []

        adaptive_limit = min(
            best_distance + adaptive_margin,
            max_distance
        )

        filtered_results = [
            (chunk, distance_value)
            for chunk, distance_value in results
            if float(distance_value) <= adaptive_limit
        ]
        
        return [
            {
                "content": chunk.content,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "distance": float(distance_value),
            }
            for chunk, distance_value in filtered_results
        ]
