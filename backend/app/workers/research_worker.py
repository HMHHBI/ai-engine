from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from app.core.config import settings
from app.core.logging import correlation_id_var
from app.db.session import session_scope
from app.services.research_execution import (
    execute_research_run,
    recover_abandoned_research_runs,
)

logger = logging.getLogger(__name__)

RESEARCH_RUN_QUEUE = "ai:research:runs"
RESEARCH_RUN_CONSUMER_GROUP = "research-workers"
RESEARCH_RUN_PAYLOAD_FIELD = "payload"

_research_redis_client: aioredis.Redis | None = None
_research_redis_loop: asyncio.AbstractEventLoop | None = None


def get_research_redis() -> aioredis.Redis:
    global _research_redis_client, _research_redis_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if (
        _research_redis_client is None
        or _research_redis_loop is not current_loop
        or current_loop is None
        or current_loop.is_closed()
    ):
        _research_redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        _research_redis_loop = current_loop
    return _research_redis_client


class ResearchRunDispatcher:
    @staticmethod
    async def ensure_consumer_group(
        redis: aioredis.Redis | None = None,
    ) -> None:
        client = redis or get_research_redis()
        try:
            await client.xgroup_create(
                name=RESEARCH_RUN_QUEUE,
                groupname=RESEARCH_RUN_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    async def enqueue(
        *,
        run_id: int,
        correlation_id: str | None = None,
        redis: aioredis.Redis | None = None,
    ) -> str:
        client = redis or get_research_redis()
        await ResearchRunDispatcher.ensure_consumer_group(redis=client)
        payload = json.dumps(
            {
                "run_id": run_id,
                "correlation_id": correlation_id or correlation_id_var.get(),
            }
        )
        message_id = await client.xadd(
            RESEARCH_RUN_QUEUE,
            {RESEARCH_RUN_PAYLOAD_FIELD: payload},
        )
        logger.info(
            "research_run_enqueued",
            extra={
                "event": "research_run_enqueued",
                "run_id": run_id,
                "message_id": message_id,
            },
        )
        return message_id


def build_research_worker_id() -> str:
    hostname = socket.gethostname()
    pid = os.getpid()
    token = uuid.uuid4().hex[:8]
    return f"research-worker:{hostname}:{pid}:{token}"


async def run_research_job_in_background(
    *,
    run_id: int,
    correlation_id: str | None = None,
) -> None:
    """Fallback in-process executor when Redis broker is unavailable."""
    token = correlation_id_var.set(correlation_id) if correlation_id else None
    try:
        with session_scope() as db:
            await execute_research_run(
                db,
                run_id=run_id,
                correlation_id=correlation_id,
                raise_on_error=False,
            )
    finally:
        if token is not None:
            correlation_id_var.reset(token)


class ResearchRunWorker:
    def __init__(
        self,
        *,
        worker_id: str | None = None,
        redis: Any | None = None,
        concurrency: int = 2,
        recovery_interval_seconds: float = 30.0,
    ) -> None:
        self.worker_id = worker_id or build_research_worker_id()
        self._redis = redis
        self._semaphore = asyncio.Semaphore(concurrency)
        self.recovery_interval_seconds = recovery_interval_seconds
        self._running = False

    @property
    def redis(self):
        if self._redis is None:
            self._redis = get_research_redis()
        return self._redis

    async def process_message(self, message_id: str, fields: dict[str, Any]) -> None:
        async with self._semaphore:
            raw_payload = fields.get(RESEARCH_RUN_PAYLOAD_FIELD)
            try:
                data = json.loads(raw_payload) if raw_payload else {}
                run_id = int(data["run_id"])
                cid = data.get("correlation_id")
            except Exception:
                logger.warning(
                    "research_worker_malformed_message",
                    extra={"message_id": message_id},
                )
                await self.redis.xack(
                    RESEARCH_RUN_QUEUE, RESEARCH_RUN_CONSUMER_GROUP, message_id
                )
                return

            token = correlation_id_var.set(cid) if cid else None
            try:
                with session_scope() as db:
                    await execute_research_run(
                        db,
                        run_id=run_id,
                        worker_id=self.worker_id,
                        correlation_id=cid,
                        raise_on_error=False,
                    )
            finally:
                if token is not None:
                    correlation_id_var.reset(token)

            await self.redis.xack(
                RESEARCH_RUN_QUEUE, RESEARCH_RUN_CONSUMER_GROUP, message_id
            )

    async def _recovery_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.recovery_interval_seconds)
                def _recover() -> list[int]:
                    with session_scope() as db:
                        return recover_abandoned_research_runs(db)

                requeued_ids = await asyncio.to_thread(_recover)
                for run_id in requeued_ids:
                    await ResearchRunDispatcher.enqueue(
                        run_id=run_id,
                        redis=self.redis,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("research_worker_recovery_loop_failed")

    async def run(self) -> None:
        self._running = True
        recovery_task: asyncio.Task | None = None
        try:
            await ResearchRunDispatcher.ensure_consumer_group(redis=self.redis)
            # Recover any runs stranded across a process restart immediately on boot
            def _boot_recover() -> list[int]:
                with session_scope() as db:
                    return recover_abandoned_research_runs(db)

            for run_id in await asyncio.to_thread(_boot_recover):
                await ResearchRunDispatcher.enqueue(run_id=run_id, redis=self.redis)

            recovery_task = asyncio.create_task(self._recovery_loop())
            logger.info(
                "research_worker_started",
                extra={"event": "research_worker_started", "worker_id": self.worker_id},
            )

            while self._running:
                try:
                    entries = await self.redis.xreadgroup(
                        groupname=RESEARCH_RUN_CONSUMER_GROUP,
                        consumername=self.worker_id,
                        streams={RESEARCH_RUN_QUEUE: ">"},
                        count=4,
                        block=2000,
                    )
                    if not entries:
                        continue
                    for _stream_name, messages in entries:
                        for message_id, fields in messages:
                            asyncio.create_task(
                                self.process_message(message_id, fields)
                            )
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("research_worker_poll_error")
                    await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            if recovery_task is not None:
                recovery_task.cancel()
                await asyncio.gather(recovery_task, return_exceptions=True)
