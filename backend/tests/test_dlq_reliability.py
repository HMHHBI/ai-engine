import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.document_job_dlq import (
    DocumentJobDLQService,
    DOCUMENT_JOB_DLQ,
    DOCUMENT_JOB_DLQ_GROUP,
)
from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_QUEUE,
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
)


@pytest.mark.asyncio
async def test_ensure_consumer_group():
    mock_redis = AsyncMock()
    await DocumentJobDLQService.ensure_consumer_group(mock_redis)
    mock_redis.xgroup_create.assert_awaited_once_with(
        name=DOCUMENT_JOB_DLQ,
        groupname=DOCUMENT_JOB_DLQ_GROUP,
        id="0",
        mkstream=True,
    )


@pytest.mark.asyncio
async def test_forward_to_dlq_formats_metadata():
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1000-0"

    dlq_id = await DocumentJobDLQService.forward_to_dlq(
        original_message_id="999-0",
        raw_payload=json.dumps({"job_id": 42}),
        job_id=42,
        attempt=3,
        max_attempts=3,
        error_message="Connection timeout",
        error_traceback="Traceback details...",
        redis=mock_redis,
    )

    assert dlq_id == "1000-0"
    mock_redis.xadd.assert_awaited_once()
    args, kwargs = mock_redis.xadd.await_args
    assert args[0] == DOCUMENT_JOB_DLQ
    entry = args[1]
    assert entry["job_id"] == "42"
    assert entry["attempt"] == "3"
    assert entry["max_attempts"] == "3"
    assert entry["error_message"] == "Connection timeout"
    assert entry["original_message_id"] == "999-0"


@pytest.mark.asyncio
async def test_redrive_reenqueues_and_acks_dlq():
    mock_redis = AsyncMock()
    mock_redis.xrange.return_value = [
        ("1000-0", {"original_payload": '{"job_id": 42}'})
    ]
    mock_redis.xadd.return_value = "2000-0"

    res = await DocumentJobDLQService.redrive(dlq_message_id="1000-0", redis=mock_redis)

    assert res == "2000-0"
    mock_redis.xadd.assert_awaited_once_with(
        DOCUMENT_JOB_QUEUE,
        {DOCUMENT_JOB_PAYLOAD_FIELD: '{"job_id": 42}'},
    )
    mock_redis.xack.assert_awaited_once_with(DOCUMENT_JOB_DLQ, DOCUMENT_JOB_DLQ_GROUP, "1000-0")
    mock_redis.xdel.assert_awaited_once_with(DOCUMENT_JOB_DLQ, "1000-0")


@pytest.mark.asyncio
async def test_discard_removes_from_dlq():
    mock_redis = AsyncMock()
    mock_redis.xrange.return_value = [("1000-0", {})]

    res = await DocumentJobDLQService.discard(dlq_message_id="1000-0", redis=mock_redis)

    assert res is True
    mock_redis.xack.assert_awaited_once_with(DOCUMENT_JOB_DLQ, DOCUMENT_JOB_DLQ_GROUP, "1000-0")
    mock_redis.xdel.assert_awaited_once_with(DOCUMENT_JOB_DLQ, "1000-0")


@pytest.mark.asyncio
async def test_discard_nonexistent_returns_false():
    mock_redis = AsyncMock()
    mock_redis.xrange.return_value = []

    res = await DocumentJobDLQService.discard(dlq_message_id="nonexistent-id", redis=mock_redis)

    assert res is False
    mock_redis.xack.assert_not_awaited()
    mock_redis.xdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_routes_exhausted_job_to_dlq_and_acks():
    from app.workers.document_worker import DocumentIngestionWorker
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    redis = AsyncMock()
    worker = DocumentIngestionWorker(
        worker_id="document-worker:test:dlq",
        redis=redis,
        heartbeat_interval=60.0,
    )

    failed_job = SimpleNamespace(
        id=77,
        document_id=10,
        user_id=1,
        attempt=3,
        max_attempts=3,
        status="failed",
        error_message="Repeated memory error",
    )
    doc = SimpleNamespace(id=10, user_id=1, chat_id=2)

    with patch("app.workers.document_worker.session_scope"), \
         patch("app.workers.document_worker.DocumentJobRepository") as MockJobRepo, \
         patch("app.workers.document_worker.DocumentRepository") as MockDocRepo, \
         patch("app.workers.document_worker.ChatRepository") as MockChatRepo, \
         patch("app.workers.document_worker.DocumentLifecycleService.claim_job", return_value=failed_job), \
         patch("app.workers.document_worker.DocumentLifecycleService.process_job", new_callable=AsyncMock) as mock_proc, \
         patch("app.workers.document_worker.DocumentJobDLQService.forward_to_dlq", new_callable=AsyncMock) as mock_dlq:

        mock_proc.side_effect = RuntimeError("Crash processing")
        MockJobRepo.return_value.get_by_id.return_value = failed_job
        MockDocRepo.return_value.get_owned_document.return_value = doc
        MockChatRepo.return_value.get_by_id.return_value = SimpleNamespace(embedding_provider="ollama")

        payload = json.dumps({"job_id": 77})
        await worker.process_job_message("msg-fail-77", payload)

        mock_dlq.assert_awaited_once()
        _, kwargs = mock_dlq.await_args
        assert kwargs["job_id"] == 77
        assert kwargs["attempt"] == 3
        assert kwargs["max_attempts"] == 3
        redis.xack.assert_awaited_once_with(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, "msg-fail-77")
