from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import EmbeddingProvider, settings
from app.repositories.document_repo import DocumentRepository
from app.repositories.vector_repo import VectorRepository
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    """
    Coordinates the document ingestion lifecycle.

    Lifecycle:
        processing
            ↓
        extract → chunk → embed
            ↓
        replace vectors
            ↓
          ready
    """

    EMBEDDING_CONCURRENCY = 4

    @staticmethod
    async def ingest(
        *,
        user_id: int,
        document_id: int,
        pages: list[Any],
        embedding_provider: EmbeddingProvider,
    ) -> dict[str, Any]:
        chunks = await asyncio.to_thread(
            EmbeddingService.chunk_text,
            pages,
            500,
            50,
        )

        if not chunks:
            raise ValueError("No usable document chunks were produced.")

        if len(chunks) > settings.MAX_DOCUMENT_CHUNKS:
            raise ValueError("Document produces too many chunks for processing.")

        if len(chunks) > settings.MAX_CHUNK_EMBEDDINGS:
            raise ValueError("Document exceeds the maximum embedding workload.")

        semaphore = asyncio.Semaphore(DocumentIngestionService.EMBEDDING_CONCURRENCY)

        async def generate_embedding(chunk: Any):
            async with semaphore:
                return await EmbeddingService.generate_embedding(
                    chunk.text,
                    model_provider=embedding_provider.value,
                )

        vectors = await asyncio.gather(*[generate_embedding(chunk) for chunk in chunks])

        chunks_with_embeddings = [
            (chunk, vector)
            for chunk, vector in zip(chunks, vectors)
            if vector is not None
        ]

        if len(chunks_with_embeddings) != len(chunks):
            failed_embeddings = len(chunks) - len(chunks_with_embeddings)
            logger.error(
                "document_embedding_failed",
                extra={
                    "event": "document_embedding_failed",
                    "document_id": document_id,
                    "user_id": user_id,
                    "failed_embeddings": failed_embeddings,
                    "total_chunks": len(chunks),
                },
            )
            raise RuntimeError("Document embedding failed.")

        indexed_chunks = await asyncio.to_thread(
            VectorRepository.replace_document_chunks,
            user_id=user_id,
            document_id=document_id,
            chunks_with_embeddings=chunks_with_embeddings,
            pdf_context=None,
        )

        return {
            "chunks_total": len(chunks),
            "chunks_indexed": len(indexed_chunks),
            "page_count": len(pages),
            "embedding_provider": embedding_provider.value,
        }
