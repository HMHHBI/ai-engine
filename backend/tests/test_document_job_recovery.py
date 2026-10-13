import json
from unittest.mock import AsyncMock, patch
import pytest

from app.services.document_job_recovery import DocumentJobRecoveryService


@pytest.mark.asyncio
async def test_recovery_requeues_stale_job():
    redis = AsyncMock()
    with patch.object(
        DocumentJobRecoveryService,
        "_recover_database_state",
        return_value="requeued",
    ), patch(
        "app.services.document_job_recovery.DocumentJobDispatcher.enqueue",
        new_callable=AsyncMock,
    ) as enqueue:
        result = await DocumentJobRecoveryService.recover_message(
            message_id="1-0",
            raw_payload=json.dumps({"job_id": 42}),
            redis=redis,
            worker_id="worker-recovery",
        )

    assert result == "requeued"
    enqueue.assert_awaited_once_with(
        job_id=42,
        redis=redis,
    )
    redis.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_discards_invalid_payload():
    redis = AsyncMock()
    result = await DocumentJobRecoveryService.recover_message(
        message_id="2-0",
        raw_payload="invalid-json",
        redis=redis,
        worker_id="worker-recovery",
    )

    assert result == "discarded"
    redis.xack.assert_awaited_once()
