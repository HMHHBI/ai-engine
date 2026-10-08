from __future__ import annotations

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
from app.repositories.document_job_repo import DocumentJobRepository, DocumentJobTransitionError
from app.repositories.document_repo import DocumentRepository
from app.services.document_job_dispatcher import (
    DOCUMENT_JOB_CONSUMER_GROUP,
    DOCUMENT_JOB_PAYLOAD_FIELD,
    DOCUMENT_JOB_QUEUE,
    DocumentJobDispatcher,
    get_document_redis,
)
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
    ) -> None:
        self.worker_id = worker_id or build_worker_id()
        self._redis = redis
        self.heartbeat_interval = (
            heartbeat_interval
            if heartbeat_interval is not None
            else getattr(settings, "HEARTBEAT_INTERVAL_SECONDS", 15.0)
        )
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

    async def _heartbeat_loop(self, job_id: int, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.heartbeat_interval)
                break
            except asyncio.TimeoutError:
                pass

            try:
                # Check for cancellation during heartbeat
                is_cancelled = await asyncio.to_thread(
                    DocumentLifecycleService.is_cancel_requested,
                    job_id=job_id,
                    worker_id=self.worker_id,
                )
                if is_cancelled:
                    logger.info(f"Cancellation requested observed by heartbeat for job {job_id}")
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
        try:
            data = json.loads(raw_payload)
            job_id = int(data["job_id"])
        except Exception as e:
            logger.error(f"Malformed stream message {message_id}: {raw_payload} ({e})")
            await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            return

        # 1. Retrieve Job and Chat context
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
            logger.error(f"Invalid job {job_id} or unowned document: acknowledging and discarding")
            await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)
            return

        embedding_provider = await self._resolve_embedding_provider(doc.chat_id, doc.user_id)

        # 2. Run ingestion lifecycle with concurrent heartbeat monitor
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id, stop_event))

        try:
            await DocumentLifecycleService.process_job(
                job_id=job_id,
                worker_id=self.worker_id,
                embedding_provider=embedding_provider,
            )
        finally:
            stop_event.set()
            await heartbeat_task
            # Always acknowledge message once terminal state is persisted
            await self.redis.xack(DOCUMENT_JOB_QUEUE, DOCUMENT_JOB_CONSUMER_GROUP, message_id)

    async def run(self, once: bool = False) -> None:
        self._running = True
        await DocumentJobDispatcher.ensure_consumer_group(redis=self.redis)
        logger.info(f"Worker {self.worker_id} started listening on {DOCUMENT_JOB_QUEUE}")

        while self._running:
            try:
                entries = await self.redis.xreadgroup(
                    groupname=DOCUMENT_JOB_CONSUMER_GROUP,
                    consumername=self.worker_id,
                    streams={DOCUMENT_JOB_QUEUE: ">"},
                    count=1,
                    block=2000,
                )

                if not entries:
                    if once:
                        break
                    continue

                for stream_name, messages in entries:
                    for message_id, fields in messages:
                        raw_payload = fields.get(DOCUMENT_JOB_PAYLOAD_FIELD)
                        if raw_payload:
                            await self.process_job_message(message_id, raw_payload)

                if once:
                    break

            except asyncio.CancelledError:
                logger.info(f"Worker {self.worker_id} shutting down...")
                break
            except Exception as e:
                logger.exception(f"Error in worker stream read loop: {e}")
                await asyncio.sleep(1.0)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    worker = DocumentIngestionWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
