import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest

from app.core.config import EmbeddingProvider
from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_QUEUE,
)
from app.services.document_lifecycle_service import DocumentLifecycleService
from app.workers.document_worker import DocumentIngestionWorker


@pytest.mark.asyncio
async def test_worker_processes_job_and_acknowledges():
    redis = AsyncMock()
    worker = DocumentIngestionWorker(
        worker_id="document-worker:test:1",
        redis=redis,
        heartbeat_interval=60.0,
    )

    job = SimpleNamespace(id=42, document_id=100, user_id=7)
    doc = SimpleNamespace(id=100, user_id=7, chat_id=55)

    with patch.object(DocumentLifecycleService, "process_job", new_callable=AsyncMock) as mock_process:
        with patch("app.workers.document_worker.session_scope"):
            with patch("app.workers.document_worker.DocumentJobRepository") as MockJobRepo,                  patch("app.workers.document_worker.DocumentRepository") as MockDocRepo,                  patch("app.workers.document_worker.ChatRepository") as MockChatRepo:

                MockJobRepo.return_value.get_by_id.return_value = job
                MockDocRepo.return_value.get_owned_document.return_value = doc
                MockChatRepo.return_value.get_by_id.return_value = SimpleNamespace(embedding_provider="ollama")

                payload = json.dumps({"job_id": 42})
                await worker.process_job_message("msg-101", payload)

                mock_process.assert_awaited_once_with(
                    document_id=100,
                    user_id=7,
                    job_id=42,
                    embedding_provider=EmbeddingProvider.OLLAMA,
                    worker_id="document-worker:test:1",
                )
                redis.xack.assert_awaited_once_with(
                    DOCUMENT_JOB_QUEUE,
                    DOCUMENT_JOB_CONSUMER_GROUP,
                    "msg-101",
                )


@pytest.mark.asyncio
async def test_worker_discards_and_acks_corrupted_message():
    redis = AsyncMock()
    worker = DocumentIngestionWorker(
        worker_id="document-worker:test:2",
        redis=redis,
    )

    await worker.process_job_message("msg-corrupted", "not-json-content")
    redis.xack.assert_awaited_once_with(
        DOCUMENT_JOB_QUEUE,
        DOCUMENT_JOB_CONSUMER_GROUP,
        "msg-corrupted",
    )
