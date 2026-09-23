from __future__ import annotations

import asyncio
from unittest.mock import patch
import pytest

from app.core.config import EmbeddingProvider
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.embedding_service import DocumentChunk, EmbeddingService
from app.repositories.vector_repo import VectorRepository


@pytest.fixture(autouse=True)
def reset_document_ingestion_semaphore():
    DocumentIngestionService._embedding_semaphore = None
    yield
    DocumentIngestionService._embedding_semaphore = None


@pytest.mark.asyncio
async def test_document_ingestion_enforces_process_level_concurrency_bound():
    """
    Asserts that across multiple concurrent ingestion tasks, the total number
    of simultaneous in-flight embedding calls never exceeds EMBEDDING_CONCURRENCY.
    """
    limit = DocumentIngestionService.EMBEDDING_CONCURRENCY
    active_calls = 0
    max_active_observed = 0
    counter_lock = asyncio.Lock()

    async def simulated_embedding(text: str, model_provider: str):
        nonlocal active_calls, max_active_observed
        async with counter_lock:
            active_calls += 1
            if active_calls > max_active_observed:
                max_active_observed = active_calls

        await asyncio.sleep(0.02)

        async with counter_lock:
            active_calls -= 1

        return [0.1, 0.2, 0.3]

    concurrent_requests = 10
    chunks_per_request = 4

    def generate_chunks(req_id: int):
        return [
            DocumentChunk(
                text=f"Sample text content for chunk {i}",
                page_number=1,
                chunk_index=i,
            )
            for i in range(chunks_per_request)
        ]

    with patch.object(
        EmbeddingService,
        "chunk_text",
        side_effect=lambda pages, *args: generate_chunks(0),
    ), patch.object(
        EmbeddingService,
        "generate_embedding",
        side_effect=simulated_embedding,
    ), patch.object(
        VectorRepository,
        "replace_document_chunks",
        return_value=[],
    ):
        tasks = [
            DocumentIngestionService.ingest(
                user_id=1,
                document_id=req_id,
                pages=["page_data"],
                embedding_provider=EmbeddingProvider.OLLAMA,
            )
            for req_id in range(1, concurrent_requests + 1)
        ]
        results = await asyncio.gather(*tasks)

    assert len(results) == concurrent_requests
    assert max_active_observed > 1, "Concurrency test did not run concurrently"
    assert max_active_observed <= limit, (
        f"Embedding concurrency violated: observed {max_active_observed} "
        f"simultaneous calls, exceeding configured bound of {limit}"
    )


@pytest.mark.asyncio
async def test_chat_upload_shares_document_ingestion_semaphore():
    """
    Verifies that chat.py retrieves the same singleton semaphore instance 
    as DocumentIngestionService.
    """
    sem1 = DocumentIngestionService.get_embedding_semaphore()
    sem2 = DocumentIngestionService.get_embedding_semaphore()
    assert sem1 is sem2
    assert sem1._value == DocumentIngestionService.EMBEDDING_CONCURRENCY
