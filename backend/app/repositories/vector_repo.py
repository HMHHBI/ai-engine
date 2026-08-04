from sqlalchemy.orm import Session
from app.db.models import DocumentChunk


class VectorRepository:
    @staticmethod
    def store_document_chunks(
        db: Session, chat_id: int, chunks_with_embeddings: list[tuple[str, list[float]]]
    ) -> list[DocumentChunk]:
        """
        Batch insert document chunks and their vector embeddings into PostgreSQL (pgvector).
        """
        db_objs = [
            DocumentChunk(chat_id=chat_id, content=content, embedding=embedding)
            for content, embedding in chunks_with_embeddings
        ]
        db.add_all(db_objs)
        db.commit()
        for obj in db_objs:
            db.refresh(obj)
        return db_objs

    @staticmethod
    def search_similar_chunks(
        db: Session, chat_id: int, query_vector: list[float], top_k: int = 4
    ) -> list[str]:
        """
        Perform Cosine Distance (<=>) vector search over stored document embeddings.
        """
        results = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.chat_id == chat_id)
            .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
            .limit(top_k)
            .all()
        )
        return [chunk.content for chunk in results]
