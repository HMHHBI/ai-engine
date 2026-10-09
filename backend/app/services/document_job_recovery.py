from __future__ import annotations
from app.db.models import Document, DocumentJob, DocumentJobStatus
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.session import session_scope
from app.repositories.document_job_repo import DocumentJobRepository
from app.repositories.document_repo import DocumentRepository
from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
    DOCUMENT_JOB_QUEUE,
    DocumentJobDispatcher,
    get_document_redis,
)

logger = logging.getLogger(__name__)


class DocumentJobRecoveryService:
    @staticmethod
    def _parse_job_id(raw_payload: str) -> int | None:
        try:
            payload = json.loads(raw_payload)
            if not isinstance(payload, dict):
                return None
            raw_job_id = payload.get("job_id")
            if isinstance(raw_job_id, bool):
                return None
            job_id = int(raw_job_id)
            if job_id <= 0:
                return None
            return job_id
        except Exception:
            return None

    @classmethod
    def _recover_database_state(
        cls,
        *,
        job_id: int,
        stale_threshold_seconds: float,
    ) -> str:
        """
        Reclaims or fails a job based on its heartbeat and attempts.
        Returns: 'requeued' | 'failed' | 'ignored'
        """
        with session_scope() as db:
            job_repo = DocumentJobRepository(db)
            job = job_repo.get_by_id(job_id)
            if not job:
                return "ignored"

            # Terminal states are already settled
            if job.status in ("ready", "failed", "cancelled"):
                return "ignored"

            if job.status == "queued":
                return "ignored"

            # Check heartbeat freshness
            now = datetime.now(timezone.utc)
            last_activity = job.heartbeat_at or job.started_at or job.queued_at
            if last_activity and last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            cutoff = now - timedelta(seconds=stale_threshold_seconds)
            if last_activity and last_activity > cutoff:
                # Still alive
                return "ignored"

            # Stale job handling
            doc_repo = DocumentRepository(db)
            if job.attempt < job.max_attempts:
                logger.warning(
                    f"Requeueing stale job {job_id} (attempt {job.attempt}/{job.max_attempts})"
                )
                job_repo.requeue_stale(
                    job_id=job_id,
                    worker_id=job.worker_id,
                    attempt=job.attempt,
                )
                DocumentRepository.update_status(
                    document_id=job.document_id,
                    user_id=job.user_id,
                    status="processing",
                )
                return "requeued"
            else:
                logger.error(
                    f"Failing stale job {job_id}: exceeded max attempts ({job.attempt}/{job.max_attempts})"
                )
                job_repo.transition_to_failed(
                    job_id=job_id,
                    error_message=f"Job lease expired after attempt {job.attempt} and reached max attempts.",
                )
                DocumentRepository.update_status(
                    document_id=job.document_id,
                    user_id=job.user_id,
                    status="failed",
                    error_message="Job exceeded maximum retries after worker crash.",
                )
                return "failed"

    @classmethod
    async def recover_message(
        cls,
        *,
        message_id: str,
        raw_payload: str,
        redis: Any,
        worker_id: str,
        stale_threshold_seconds: float | None = None,
    ) -> str:
        threshold = (
            stale_threshold_seconds
            if stale_threshold_seconds is not None
            else getattr(settings, "DOCUMENT_JOB_STALE_AFTER_SECONDS", 60.0)
        )

        job_id = cls._parse_job_id(raw_payload)
        if job_id is None:
            # Corrupted message - ACK and drop
            await redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            return "discarded"

        result = cls._recover_database_state(
            job_id=job_id,
            stale_threshold_seconds=threshold,
        )

        if result == "requeued":
            # ACK stale PEL message and dispatch fresh one
            await redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            await DocumentJobDispatcher.enqueue(job_id=job_id, redis=redis)
        elif result == "failed":
            await redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)

        return result

    @classmethod
    async def run_autoclaim_cycle(
        cls,
        *,
        worker_id: str,
        redis: Any | None = None,
        min_idle_time_ms: int = 60000,
        batch_size: int = 10,
    ) -> int:
        client = redis or get_document_redis()
        recovered_count = 0

        try:
            # XAUTOCLAIM ai:document:jobs document-workers <worker_id> <min_idle_time> 0-0 COUNT <batch_size>
            claim_result = await client.xautoclaim(
                name=DOCUMENT_JOB_QUEUE,
                groupname=DOCUMENT_JOB_CONSUMER_GROUP,
                consumername=worker_id,
                min_idle_time=min_idle_time_ms,
                start_id="0-0",
                count=batch_size,
            )

            # claim_result structure: [next_start_id, [(message_id, fields), ...], (deleted_ids)]
            messages = claim_result[1] if len(claim_result) > 1 else []

            for message_id, fields in messages:
                raw_payload = fields.get(DOCUMENT_JOB_PAYLOAD_FIELD)
                if raw_payload:
                    res = await cls.recover_message(
                        message_id=message_id,
                        raw_payload=raw_payload,
                        redis=client,
                        worker_id=worker_id,
                    )
                    if res in ("requeued", "failed"):
                        recovered_count += 1

        except Exception as e:
            logger.warning(f"Error during XAUTOCLAIM cycle: {e}")

        return recovered_count
    def recover_stale_job(
        self,
        *,
        job_id: int,
        worker_id: str,
        attempt: int,
        stale_threshold_seconds: float,
    ) -> Optional[DocumentJob]:
        """
        Atomically recovers a stale job under row lock.
        Verifies that worker_id and attempt still match, and that heartbeat_at is still stale.
        Transitions job + document in one atomic transaction.
        """
        with session_scope() as db:
            job = (
                db.query(DocumentJob)
                .filter(DocumentJob.id == job_id)
                .with_for_update()
                .first()
            )
            if not job:
                return None

            if (
                job.status != DocumentJobStatus.PROCESSING.value
                or job.worker_id != worker_id
                or job.attempt != attempt
            ):
                logger.info(
                    "Job %s was modified by another worker/recovery; skipping",
                    job_id,
                )
                return None

            now = datetime.now(timezone.utc)
            # Re-verify stale heartbeat under the lock
            last_activity = job.heartbeat_at or job.started_at
            if last_activity:
                # Ensure timezone aware
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                age = (now - last_activity).total_seconds()
                if age < stale_threshold_seconds:
                    logger.info(
                        "Job %s heartbeat was refreshed (age=%.1fs < %.1fs); skipping recovery",
                        job_id,
                        age,
                        stale_threshold_seconds,
                    )
                    return None

            doc = (
                db.query(Document)
                .filter(Document.id == job.document_id, Document.user_id == job.user_id)
                .with_for_update()
                .first()
            )

            # If attempts exhausted, fail both job and document
            if job.attempt >= job.max_attempts:
                error_msg = f"Job exceeded max_attempts ({job.max_attempts}) due to worker crash or timeout"
                job.status = DocumentJobStatus.FAILED.value
                job.error_message = error_msg
                job.worker_id = None
                job.heartbeat_at = None
                job.finished_at = now
                if doc:
                    doc.status = "failed"
                    doc.error_message = error_msg
                db.commit()
                db.refresh(job)
                logger.warning("Job %s marked terminal FAILED after exceeding max attempts", job_id)
                return job

            # Requeue for retry
            job.status = DocumentJobStatus.QUEUED.value
            job.worker_id = None
            job.started_at = None
            job.heartbeat_at = None
            job.queued_at = now
            if doc:
                doc.status = "queued"
            db.commit()
            db.refresh(job)
            logger.info("Job %s atomically requeued for next attempt", job_id)
            return job
