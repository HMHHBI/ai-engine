from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ResponseError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import correlation_id_var
from app.db.models import ResearchRun, ResearchRunOutbox
from app.db.session import session_scope
from app.services.research_execution import (
    execute_research_run,
    recover_abandoned_research_runs,
)

logger = logging.getLogger(__name__)

RESEARCH_RUN_QUEUE = "ai:research:runs"
RESEARCH_RUN_CONSUMER_GROUP = "research-workers"
RESEARCH_RUN_PAYLOAD_FIELD = "payload"
DEFAULT_PENDING_IDLE_MS = 30_000
DEFAULT_QUEUED_GRACE_SECONDS = 5.0

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


def create_research_run_outbox(
    db: Session,
    *,
    run: ResearchRun,
    correlation_id: str | None = None,
) -> ResearchRunOutbox:
    """
    Create a transactional outbox record in the caller's open DB transaction.
    Caller must have flushed `run` so `run.id` is populated before committing both together.
    """
    outbox = ResearchRunOutbox(
        research_run_id=run.id,
        workspace_id=run.workspace_id,
        status="pending",
        payload={
            "run_id": run.id,
            "workspace_id": run.workspace_id,
            "correlation_id": correlation_id or correlation_id_var.get(),
        },
        attempts=0,
    )
    db.add(outbox)
    return outbox


def reconcile_stranded_queued_runs(
    db: Session,
    *,
    grace_seconds: float = DEFAULT_QUEUED_GRACE_SECONDS,
) -> list[int]:
    """
    Ensure every `queued` research run older than `grace_seconds` has a pending
    outbox entry so no run can remain stranded indefinitely if enqueueing failed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=float(grace_seconds))
    queued_runs = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.status == "queued",
            ResearchRun.created_at <= cutoff,
        )
        .all()
    )

    reconciled_run_ids: list[int] = []
    for run in queued_runs:
        lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})
        if lifecycle.get("cancel_requested"):
            continue

        existing_pending = (
            db.query(ResearchRunOutbox.id)
            .filter(
                ResearchRunOutbox.research_run_id == run.id,
                ResearchRunOutbox.status == "pending",
            )
            .first()
        )
        if existing_pending is not None:
            continue

        create_research_run_outbox(
            db,
            run=run,
            correlation_id=lifecycle.get("correlation_id"),
        )
        reconciled_run_ids.append(run.id)

    if reconciled_run_ids:
        db.commit()
    return reconciled_run_ids


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
        outbox_id: int | None = None,
        redis: aioredis.Redis | None = None,
    ) -> str:
        client = redis or get_research_redis()
        await ResearchRunDispatcher.ensure_consumer_group(redis=client)
        body: dict[str, Any] = {
            "run_id": run_id,
            "correlation_id": correlation_id or correlation_id_var.get(),
        }
        if outbox_id is not None:
            body["outbox_id"] = outbox_id
        payload = json.dumps(body)
        message_id = await client.xadd(
            RESEARCH_RUN_QUEUE,
            {RESEARCH_RUN_PAYLOAD_FIELD: payload},
        )
        logger.info(
            "research_run_enqueued",
            extra={
                "event": "research_run_enqueued",
                "run_id": run_id,
                "outbox_id": outbox_id,
                "message_id": message_id,
            },
        )
        return message_id

    @staticmethod
    async def publish_outbox_event(
        db: Session,
        *,
        outbox_id: int,
        redis: aioredis.Redis | None = None,
    ) -> bool:
        """
        Publish a single pending outbox record to Redis Stream and mark it `published`
        only after `XADD` succeeds. Idempotent across concurrent dispatchers.
        """
        entry = (
            db.query(ResearchRunOutbox)
            .filter(
                ResearchRunOutbox.id == outbox_id,
                ResearchRunOutbox.status == "pending",
            )
            .with_for_update(skip_locked=True)
            .first()
        )
        if entry is None:
            return False

        run = (
            db.query(ResearchRun)
            .filter(ResearchRun.id == entry.research_run_id)
            .first()
        )
        if run is None or run.status != "queued":
            entry.status = "published"
            entry.published_at = datetime.now(timezone.utc)
            db.commit()
            return False

        payload = dict(entry.payload or {})
        try:
            await ResearchRunDispatcher.enqueue(
                run_id=entry.research_run_id,
                correlation_id=payload.get("correlation_id"),
                outbox_id=entry.id,
                redis=redis,
            )
        except Exception as exc:
            entry.attempts = int(entry.attempts or 0) + 1
            entry.last_error = str(exc)[:500]
            db.commit()
            raise

        entry.status = "published"
        entry.published_at = datetime.now(timezone.utc)
        entry.last_error = None
        db.commit()
        return True

    @staticmethod
    async def flush_pending_outbox(
        db: Session,
        *,
        redis: aioredis.Redis | None = None,
        limit: int = 50,
    ) -> int:
        """
        Sweep pending outbox records and publish them to Redis Stream.
        Returns count of newly published records.
        """
        pending_ids = [
            row[0]
            for row in (
                db.query(ResearchRunOutbox.id)
                .filter(ResearchRunOutbox.status == "pending")
                .order_by(ResearchRunOutbox.id.asc())
                .limit(limit)
                .all()
            )
        ]
        published = 0
        for outbox_id in pending_ids:
            try:
                if await ResearchRunDispatcher.publish_outbox_event(
                    db, outbox_id=outbox_id, redis=redis
                ):
                    published += 1
            except Exception:
                logger.warning(
                    "research_outbox_publish_deferred",
                    extra={"outbox_id": outbox_id},
                )
        return published


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
    """Legacy helper retained for direct in-process execution callers."""
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
        recovery_interval_seconds: float = 15.0,
        pending_idle_ms: int = DEFAULT_PENDING_IDLE_MS,
        queued_grace_seconds: float = DEFAULT_QUEUED_GRACE_SECONDS,
    ) -> None:
        self.worker_id = worker_id or build_research_worker_id()
        self._redis = redis
        self._semaphore = asyncio.Semaphore(concurrency)
        self.recovery_interval_seconds = recovery_interval_seconds
        self.pending_idle_ms = pending_idle_ms
        self.queued_grace_seconds = queued_grace_seconds
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

    async def reclaim_abandoned_messages(self, count: int = 10) -> int:
        """
        Reclaim abandoned unacknowledged Redis Stream entries using XAUTOCLAIM
        and route them through atomic DB lease claiming before XACK.
        """
        await ResearchRunDispatcher.ensure_consumer_group(redis=self.redis)
        reclaimed_count = 0
        start_id = "0-0"

        while True:
            result = await self.redis.xautoclaim(
                name=RESEARCH_RUN_QUEUE,
                groupname=RESEARCH_RUN_CONSUMER_GROUP,
                consumername=self.worker_id,
                min_idle_time=self.pending_idle_ms,
                start_id=start_id,
                count=count,
            )
            if not result or len(result) < 2:
                break

            next_start_id = result[0]
            messages = result[1] or []
            if not messages:
                break

            for message_id, fields in messages:
                reclaimed_count += 1
                logger.info(
                    "research_worker_reclaimed_pending_message",
                    extra={
                        "event": "research_worker_reclaimed_pending_message",
                        "worker_id": self.worker_id,
                        "message_id": message_id,
                    },
                )
                await self.process_message(message_id, fields)

            if not next_start_id or next_start_id == "0-0":
                break
            start_id = next_start_id

        return reclaimed_count

    async def run_recovery_cycle(self) -> dict[str, int]:
        """
        Execute one full durability reconciliation pass:
        1. Reclaim abandoned Redis Stream pending entries (XAUTOCLAIM).
        2. Recover expired active DB leases back to `queued` + enqueue outbox entries.
        3. Reconcile stranded `queued` runs without pending outbox entries.
        4. Flush all pending outbox records to Redis Stream.
        """
        reclaimed_messages = await self.reclaim_abandoned_messages()

        def _db_reconcile() -> tuple[list[int], list[int]]:
            with session_scope() as db:
                requeued = recover_abandoned_research_runs(db)
                for run_id in requeued:
                    run = db.query(ResearchRun).filter(ResearchRun.id == run_id).first()
                    if run is not None:
                        lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})
                        create_research_run_outbox(
                            db,
                            run=run,
                            correlation_id=lifecycle.get("correlation_id"),
                        )
                if requeued:
                    db.commit()
                stranded = reconcile_stranded_queued_runs(
                    db, grace_seconds=self.queued_grace_seconds
                )
                return requeued, stranded

        requeued_ids, stranded_ids = await asyncio.to_thread(_db_reconcile)

        with session_scope() as db:
            published_count = await ResearchRunDispatcher.flush_pending_outbox(
                db, redis=self.redis
            )

        return {
            "reclaimed_messages": reclaimed_messages,
            "requeued_runs": len(requeued_ids),
            "reconciled_queued_runs": len(stranded_ids),
            "published_outbox": published_count,
        }

    async def _recovery_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.recovery_interval_seconds)
                if not self._running:
                    break
                await self.run_recovery_cycle()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("research_worker_recovery_loop_failed")

    async def run(self) -> None:
        self._running = True
        recovery_task: asyncio.Task | None = None
        try:
            await ResearchRunDispatcher.ensure_consumer_group(redis=self.redis)
            await self.run_recovery_cycle()

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
