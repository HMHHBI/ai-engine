from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from app.core.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_JOB_QUEUE = "ai:document:jobs"
DOCUMENT_JOB_CONSUMER_GROUP = "document-workers"
DOCUMENT_JOB_PAYLOAD_FIELD = "payload"

_redis_client: aioredis.Redis | None = None
_redis_loop: asyncio.AbstractEventLoop | None = None


def get_document_redis() -> aioredis.Redis:
    global _redis_client, _redis_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is None or _redis_loop is not current_loop or current_loop is None or current_loop.is_closed():
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        _redis_loop = current_loop
    return _redis_client


class DocumentJobDispatcher:
    @staticmethod
    async def ensure_consumer_group(
        redis: aioredis.Redis | None = None,
    ) -> None:
        client = redis or get_document_redis()
        try:
            await client.xgroup_create(
                name=DOCUMENT_JOB_QUEUE,
                groupname=DOCUMENT_JOB_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                f"Created consumer group {DOCUMENT_JOB_CONSUMER_GROUP} on {DOCUMENT_JOB_QUEUE}"
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    async def enqueue(
        *,
        job_id: int,
        redis: aioredis.Redis | None = None,
    ) -> str:
        client = redis or get_document_redis()
        await DocumentJobDispatcher.ensure_consumer_group(redis=client)

        payload = json.dumps({"job_id": job_id})
        message_id = await client.xadd(
            DOCUMENT_JOB_QUEUE,
            {DOCUMENT_JOB_PAYLOAD_FIELD: payload},
        )
        logger.info(
            f"Enqueued document job {job_id} to {DOCUMENT_JOB_QUEUE} (message_id: {message_id})"
        )
        return message_id
