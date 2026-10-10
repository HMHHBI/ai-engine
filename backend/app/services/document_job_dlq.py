from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from redis.exceptions import ResponseError

from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
    DOCUMENT_JOB_QUEUE,
    get_document_redis,
)

logger = logging.getLogger(__name__)

DOCUMENT_JOB_DLQ = "ingestion:dlq"
DOCUMENT_JOB_DLQ_GROUP = "document-dlq-operators"
MAX_DLQ_ERROR_LENGTH = 4000
MAX_DLQ_TRACEBACK_LENGTH = 12000


class DocumentJobDLQService:
    @staticmethod
    async def ensure_consumer_group(redis: Any | None = None) -> None:
        client = redis or get_document_redis()
        try:
            await client.xgroup_create(
                name=DOCUMENT_JOB_DLQ,
                groupname=DOCUMENT_JOB_DLQ_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error("Failed to ensure DLQ consumer group: %s", e)
                raise

    @classmethod
    async def forward_to_dlq(
        cls,
        *,
        original_message_id: str,
        raw_payload: str,
        job_id: int | None = None,
        attempt: int | None = None,
        max_attempts: int | None = None,
        error_message: str | None = None,
        error_traceback: str | None = None,
        redis: Any | None = None,
    ) -> str:
        client = redis or get_document_redis()
        await cls.ensure_consumer_group(client)

        truncated_err = (error_message or "")[:MAX_DLQ_ERROR_LENGTH]
        truncated_tb = (error_traceback or "")[:MAX_DLQ_TRACEBACK_LENGTH]

        dlq_entry = {
            "dlq_id": str(uuid4()),
            "original_message_id": str(original_message_id),
            "original_payload": str(raw_payload),
            "job_id": str(job_id) if job_id is not None else "",
            "attempt": str(attempt) if attempt is not None else "",
            "max_attempts": str(max_attempts) if max_attempts is not None else "",
            "error_message": truncated_err,
            "error_traceback": truncated_tb,
            "forwarded_at": datetime.now(timezone.utc).isoformat(),
        }

        dlq_msg_id = await client.xadd(DOCUMENT_JOB_DLQ, dlq_entry)
        logger.warning(
            "Forwarded failed job %s (orig_id=%s) to DLQ %s with msg_id=%s",
            job_id,
            original_message_id,
            DOCUMENT_JOB_DLQ,
            dlq_msg_id,
        )
        return dlq_msg_id

    @classmethod
    async def redrive(
        cls,
        *,
        dlq_message_id: str,
        redis: Any | None = None,
    ) -> str | None:
        client = redis or get_document_redis()
        messages = await client.xrange(DOCUMENT_JOB_DLQ, min=dlq_message_id, max=dlq_message_id, count=1)
        if not messages:
            logger.warning("DLQ message %s not found for redrive", dlq_message_id)
            return None

        msg_id, fields = messages[0]
        raw_payload = fields.get("original_payload")
        if not raw_payload:
            logger.error("DLQ message %s missing original_payload", dlq_message_id)
            return None

        new_msg_id = await client.xadd(DOCUMENT_JOB_QUEUE, {DOCUMENT_JOB_PAYLOAD_FIELD: raw_payload})
        # Acknowledge and delete from DLQ to avoid double redrive
        await client.xack(DOCUMENT_JOB_DLQ, DOCUMENT_JOB_DLQ_GROUP, dlq_message_id)
        await client.xdel(DOCUMENT_JOB_DLQ, dlq_message_id)

        logger.info(
            "Successfully redrove DLQ message %s into %s as %s",
            dlq_message_id,
            DOCUMENT_JOB_QUEUE,
            new_msg_id,
        )
        return new_msg_id

    @classmethod
    async def discard(
        cls,
        *,
        dlq_message_id: str,
        redis: Any | None = None,
    ) -> bool:
        client = redis or get_document_redis()
        messages = await client.xrange(DOCUMENT_JOB_DLQ, min=dlq_message_id, max=dlq_message_id, count=1)
        if not messages:
            return False

        await client.xack(DOCUMENT_JOB_DLQ, DOCUMENT_JOB_DLQ_GROUP, dlq_message_id)
        await client.xdel(DOCUMENT_JOB_DLQ, dlq_message_id)
        logger.info("Discarded DLQ message %s", dlq_message_id)
        return True
