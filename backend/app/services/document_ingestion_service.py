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
    _embedding_semaphore: asyncio.Semaphore | None = None
    _embedding_semaphore_loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def get_embedding_semaphore(cls) -> asyncio.Semaphore:
        """
        Returns a process-level shared semaphore bound strictly to the current running event loop.
        Re-initializes cleanly if the running event loop has changed or closed.
        """
        current_loop = asyncio.get_running_loop()
        if cls._embedding_semaphore is None or cls._embedding_semaphore_loop is not current_loop:
            cls._embedding_semaphore = asyncio.Semaphore(cls.EMBEDDING_CONCURRENCY)
            cls._embedding_semaphore_loop = current_loop
        return cls._embedding_semaphore

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

        semaphore = DocumentIngestionService.get_embedding_semaphore()

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
