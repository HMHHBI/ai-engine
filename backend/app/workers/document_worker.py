from __future__ import annotations
from app.core.metrics import record_document_worker_success, set_document_dlq_depth, set_document_queue_pending
import traceback
from app.services.document_job_dlq import DocumentJobDLQService
from app.core.metrics import observe_document_queue_lag

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any

from app.core.config import EmbeddingProvider, settings
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_job_repo import (
    DocumentJobOwnershipError,
    DocumentJobRepository,
    DocumentJobTransitionError,
)
from app.repositories.document_repo import DocumentRepository
from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
    DOCUMENT_JOB_QUEUE,
    DocumentJobDispatcher,
    get_document_redis,
)
from app.services.document_job_recovery import DocumentJobRecoveryService
from app.services.document_lifecycle_service import DocumentLifecycleService

logger = logging.getLogger(__name__)


def build_worker_id() -> str:
    hostname = socket.gethostname()
    pid = os.getpid()
    token = uuid.uuid4().hex[:8]
    return f"document-worker:{hostname}:{pid}:{token}"


class DocumentIngestionWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        redis: Any | None = None,
        heartbeat_interval: float | None = None,
        concurrency: int | None = None,
    ) -> None:
        self.worker_id = worker_id or build_worker_id()
        self._redis = redis
        self.heartbeat_interval = (
            heartbeat_interval
            if heartbeat_interval is not None
            else getattr(settings, "HEARTBEAT_INTERVAL_SECONDS", 15.0)
        )
        self.concurrency = (
            concurrency
            if concurrency is not None
            else getattr(settings, "DOCUMENT_WORKER_CONCURRENCY", 4)
        )
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._running = False

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_document_redis()
        return self._redis

    async def _update_heartbeat(self, job_id: int) -> None:
        def _sync_update():
            with session_scope() as db:
                repo = DocumentJobRepository(db)
                repo.update_heartbeat(job_id=job_id, worker_id=self.worker_id)

        await asyncio.to_thread(_sync_update)

    async def _heartbeat_loop(
        self,
        job_id: int,
        stop_event: asyncio.Event,
        process_task: Optional[asyncio.Task] = None,
    ) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.heartbeat_interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                is_cancelled = await asyncio.to_thread(
                    DocumentLifecycleService.is_cancel_requested,
                    job_id=job_id,
                    worker_id=self.worker_id,
                )
                if is_cancelled:
                    logger.info(f"Cancellation observed by heartbeat for job {job_id}; cancelling processing task")
                    if process_task and not process_task.done():
                        process_task.cancel()
                    break

                await self._update_heartbeat(job_id)
            except Exception as e:
                logger.warning(f"Heartbeat update failed for job {job_id}: {e}")

    async def _resolve_embedding_provider(self, chat_id: int, user_id: int) -> EmbeddingProvider:
        def _get_chat():
            with session_scope() as db:
                repo = ChatRepository(db)
                return repo.get_by_id(chat_id=chat_id, user_id=user_id)

        chat = await asyncio.to_thread(_get_chat)
        if chat and getattr(chat, "embedding_provider", None):
            try:
                return EmbeddingProvider(chat.embedding_provider)
            except ValueError:
                pass
        return EmbeddingProvider(settings.DEFAULT_EMBEDDING_PROVIDER)

    async def process_job_message(self, message_id: str, raw_payload: str) -> None:
        observe_document_queue_lag(message_id)
        try:
            data = json.loads(raw_payload)
            job_id = int(data["job_id"])
        except Exception as e:
            logger.error(f"Malformed stream message {message_id}: {raw_payload} ({e})")
            try:
                await DocumentJobDLQService.forward_to_dlq(
                    original_message_id=message_id,
                    raw_payload=raw_payload,
                    error_message=f"Malformed message: {e}",
                    error_traceback=traceback.format_exc(),
                    redis=self.redis,
                )
            except Exception:
                logger.exception("Failed forwarding malformed message to DLQ")
            await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            return

        def _get_job_context():
            with session_scope() as db:
                job_repo = DocumentJobRepository(db)
                job = job_repo.get_by_id(job_id)
                if not job:
                    return None, None
                doc_repo = DocumentRepository(db)
                doc = doc_repo.get_owned_document(document_id=job.document_id, user_id=job.user_id)
                return job, doc

        job, doc = await asyncio.to_thread(_get_job_context)
        if not job or not doc:
            logger.error(f"Invalid job {job_id} or unowned doc: acknowledging and discarding")
            await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            return

        embedding_provider = await self._resolve_embedding_provider(doc.chat_id, doc.user_id)

        async with self._semaphore:
            stop_event = asyncio.Event()
            try:
                claimed_job = await asyncio.to_thread(
                    DocumentLifecycleService.claim_job,
                    job_id=job_id,
                    worker_id=self.worker_id,
                )
            except (DocumentJobTransitionError, DocumentJobOwnershipError) as expected_err:
                logger.warning(
                    "Job %s claim rejected (%s); acknowledging duplicate or stale message",
                    job_id,
                    expected_err,
                )
                await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
                return
            except Exception as transient_err:
                logger.exception(
                    "Transient database failure claiming job %s; leaving in PEL for recovery",
                    job_id,
                )
                raise
            proc_task = asyncio.create_task(
                DocumentLifecycleService.process_job(
                    document_id=doc.id,
                    user_id=doc.user_id,
                    job_id=job_id,
                    embedding_provider=embedding_provider,
                    worker_id=self.worker_id,
                    claimed_job=claimed_job,
                )
            )
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(job_id, stop_event, process_task=proc_task)
            )
            proc_error = None
            try:
                await proc_task
            except asyncio.CancelledError:
                logger.info(f"Processing task cancelled for job {job_id}")
                stop_event.set()
                if not heartbeat_task.done():
                    await heartbeat_task
                raise
            except Exception as exc:
                proc_error = exc
                logger.exception("Error processing job %s: %s", job_id, exc)
            finally:
                stop_event.set()
                if not heartbeat_task.done():
                    await heartbeat_task

            # Coordinate ACK / DLQ lifecycle with durable DB state
            def _check_terminal_state():
                with session_scope() as db:
                    j_repo = DocumentJobRepository(db)
                    current_j = j_repo.get_by_id(job_id)
                    if not current_j:
                        return ("completed" if proc_error is None else "failed"), 1, 3, None
                    raw_st = getattr(current_j, "status", None)
                    if raw_st is None:
                        st_str = "completed" if proc_error is None else "failed"
                    elif hasattr(raw_st, "value"):
                        st_str = raw_st.value
                    else:
                        st_str = str(raw_st)
                    return (
                        st_str,
                        getattr(current_j, "attempt", 1),
                        getattr(current_j, "max_attempts", 3),
                        getattr(current_j, "error_message", None),
                    )

            j_status, j_attempt, j_max, j_err = await asyncio.to_thread(_check_terminal_state)

            if j_status == "completed":
                record_document_worker_success()
                await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            elif j_status == "failed" and j_attempt >= j_max:
                logger.warning("Job %s exhausted retries (%s/%s); routing to DLQ", job_id, j_attempt, j_max)
                tb_str = traceback.format_exc() if proc_error else None
                await DocumentJobDLQService.forward_to_dlq(
                    original_message_id=message_id,
                    raw_payload=raw_payload,
                    job_id=job_id,
                    attempt=j_attempt,
                    max_attempts=j_max,
                    error_message=j_err or str(proc_error or "Exhausted retries"),
                    error_traceback=tb_str,
                    redis=self.redis,
                )
                await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            elif j_status == "cancelled":
                await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            else:
                logger.info("Job %s in status %s (attempt %s/%s); leaving in stream for retry recovery", job_id, j_status, j_attempt, j_max)

    async def _recovery_daemon_loop(self) -> None:
        recovery_interval = getattr(settings, "DOCUMENT_JOB_RECOVERY_INTERVAL_SECONDS", 15.0)
        idle_time_ms = int(getattr(settings, "DOCUMENT_JOB_RECOVERY_IDLE_SECONDS", 60.0) * 1000)
        batch_size = getattr(settings, "DOCUMENT_JOB_RECOVERY_BATCH_SIZE", 10)

        while self._running:
            try:
                await asyncio.sleep(recovery_interval)
                await DocumentJobRecoveryService.run_autoclaim_cycle(
                    worker_id=self.worker_id,
                    redis=self.redis,
                    min_idle_time_ms=idle_time_ms,
                    batch_size=batch_size,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Background recovery daemon error: {e}")

    async def run(self, once: bool = False) -> None:
        self._running = True
        await DocumentJobDispatcher.ensure_consumer_group(redis=self.redis)
        logger.info(f"Worker {self.worker_id} started (concurrency={self.concurrency})")

        recovery_task = None
        if not once:
            recovery_task = asyncio.create_task(self._recovery_daemon_loop())

        try:
            while self._running:
                try:
                    entries = await self.redis.xreadgroup(
                        groupname=DOCUMENT_JOB_CONSUMER_GROUP,
                        consumername=self.worker_id,
                        streams={DOCUMENT_JOB_QUEUE: ">"},
                        count=getattr(settings, "DOCUMENT_JOB_READ_COUNT", 5),
                        block=2000,
                    )

                    if not entries:
                        if once:
                            break
                        continue

                    tasks = []
                    for stream_name, messages in entries:
                        for message_id, fields in messages:
                            raw_payload = fields.get(DOCUMENT_JOB_PAYLOAD_FIELD)
                            if raw_payload:
                                tasks.append(
                                    asyncio.create_task(
                                        self.process_job_message(message_id, raw_payload)
                                    )
                                )

                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

                    if once:
                        break

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception(f"Worker read loop error: {e}")
                    await asyncio.sleep(1.0)
        finally:
            if recovery_task:
                recovery_task.cancel()
                try:
                    await recovery_task
                except asyncio.CancelledError:
                    pass


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    worker = DocumentIngestionWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
