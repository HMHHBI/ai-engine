import json
from unittest.mock import AsyncMock
import pytest
from redis.exceptions import ResponseError

from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
    DOCUMENT_JOB_QUEUE,
    DocumentJobDispatcher,
)


@pytest.mark.asyncio
async def test_enqueue_creates_consumer_group_and_minimal_payload():
    redis = AsyncMock()
    redis.xadd.return_value = "1234567890-0"

    message_id = await DocumentJobDispatcher.enqueue(
        job_id=42,
        redis=redis,
    )

    assert message_id == "1234567890-0"
    redis.xgroup_create.assert_awaited_once_with(
        name=DOCUMENT_JOB_QUEUE,
        groupname=DOCUMENT_JOB_CONSUMER_GROUP,
        id="0",
        mkstream=True,
    )
    redis.xadd.assert_awaited_once()
    args, kwargs = redis.xadd.await_args
    assert args[0] == DOCUMENT_JOB_QUEUE
    payload_data = json.loads(args[1][DOCUMENT_JOB_PAYLOAD_FIELD])
    assert payload_data == {"job_id": 42}
