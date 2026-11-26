from __future__ import annotations
import pytest

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, ResearchRun
from app.services.research_execution import (
    MAX_RESEARCH_RUN_ATTEMPTS,
    claim_research_run,
    execute_research_run,
    recover_abandoned_research_runs,
)
from tests.test_research_authorization_matrix import (
    add_workspace_member,
    associate_document_to_ws,
    auth_header,
    create_document_fixture,
    create_user_fixture,
    create_workspace_fixture,
)


def _seed_workspace_with_two_docs(
    db: Session,
    *,
    owner,
    prefix: str = "phase3a",
):
    ws = create_workspace_fixture(db, owner=owner, name=f"{prefix}-workspace")
    doc1 = create_document_fixture(db, user=owner, filename=f"{prefix}_paper_1.pdf")
    doc2 = create_document_fixture(db, user=owner, filename=f"{prefix}_paper_2.pdf")
    associate_document_to_ws(db, workspace_id=ws.id, document_id=doc1.id, added_by=owner.id)
    associate_document_to_ws(db, workspace_id=ws.id, document_id=doc2.id, added_by=owner.id)
    return ws, doc1, doc2


def test_async_research_run_lifecycle_persists_ordered_stages(
    client: TestClient,
    db_session: Session,
):
    owner = create_user_fixture(db_session, "owner-async@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="async-stages"
    )

    observed_statuses: list[str] = []

    async def fake_retrieve(db, **kwargs):
        db_session.expire_all()
        current = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        observed_statuses.append(current.status)
        chunk = (
            db_session.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc1.id)
            .first()
        )
        return [
            {
                "document_id": doc1.id,
                "filename": doc1.filename,
                "chunk_id": chunk.id,
                "page_number": 1,
                "score": 0.91,
                "content": chunk.content,
            }
        ]

    async def fake_synthesize(*, query: str, candidates: list[dict]):
        db_session.expire_all()
        current = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
        observed_statuses.append(current.status)
        return {
            "answer": "## Methodology\nComparative study [C1].",
            "facets": {
                "methodology": "Comparative study [C1].",
                "datasets": "Standardized benchmarks [C1].",
                "metrics": "Latency reduction [C1].",
                "findings": "Transformer latency improved [C1].",
                "limitations": "Limited to two papers [C1].",
            },
            "citations": [
                {
                    "citation_id": "C1",
                    "document_id": doc1.id,
                    "filename": doc1.filename,
                    "chunk_id": candidates[0]["chunk_id"],
                    "page_number": 1,
                    "excerpt": candidates[0]["content"][:120],
                }
            ],
            "evidence": candidates,
            "provider": "mock",
            "model": "mock-model",
        }

    with (
        patch(
            "app.api.research.ResearchRunDispatcher.enqueue",
            new=AsyncMock(side_effect=RuntimeError("skip-redis-for-deterministic-test")),
        ),
        patch("app.api.research.run_research_job_in_background", new=AsyncMock()),
    ):
        res = client.post(
            f"/workspaces/{ws.id}/research/runs?async_mode=true",
            headers=auth_header(owner),
            json={
                "query": "Compare transformer latency results",
                "document_ids": [doc1.id, doc2.id],
            },
        )

    assert res.status_code == 202, res.text
    created = res.json()
    run_id = created["id"]
    assert created["status"] == "queued"
    assert created["completed_at"] is None

    with (
        patch(
            "app.services.research_execution.retrieve_multi_document_candidates",
            side_effect=fake_retrieve,
        ),
        patch(
            "app.services.research_execution.synthesize_research_answer",
            side_effect=fake_synthesize,
        ),
    ):
        completed = asyncio.run(
            execute_research_run(
                db_session,
                run_id=run_id,
                worker_id="test-worker-1",
                correlation_id="cid-phase3a-001",
            )
        )

    assert completed is not None
    assert completed.status == "completed"
    assert observed_statuses == ["retrieving", "synthesizing"]
    lifecycle = completed.run_metadata["lifecycle"]
    assert lifecycle["correlation_id"] == "cid-phase3a-001"
    timestamps = lifecycle["stage_timestamps"]
    for stage in ("running", "retrieving", "synthesizing", "validating", "completed"):
        assert stage in timestamps


def test_sse_progress_stream_emits_stage_and_done_events(
    client: TestClient,
    db_session: Session,
):
    owner = create_user_fixture(db_session, "owner-sse@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="sse-stream"
    )

    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="SSE test query",
        status="completed",
        answer={"answer": "Done", "citations": [], "facets": None},
        run_metadata={
            "selected_document_ids": [doc1.id, doc2.id],
            "lifecycle": {
                "correlation_id": "cid-sse-123",
                "stage_timestamps": {"completed": datetime.now(timezone.utc).isoformat()},
            },
        },
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    with client.stream(
        "GET",
        f"/workspaces/{ws.id}/research/runs/{run.id}/events?poll_interval=0.05",
        headers=auth_header(owner),
    ) as stream_res:
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"].startswith("text/event-stream")
        body = "".join(stream_res.iter_text())

    assert "event: stage" in body
    assert "event: done" in body
    assert '"progress_percent": 100' in body
    assert '"status": "completed"' in body


def test_honest_cancellation_semantics_and_rbac(
    client: TestClient,
    db_session: Session,
):
    owner = create_user_fixture(db_session, "owner-cancel@phase3a.test")
    viewer = create_user_fixture(db_session, "viewer-cancel@phase3a.test")
    outsider = create_user_fixture(db_session, "outsider-cancel@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="cancel-test"
    )
    add_workspace_member(db_session, workspace_id=ws.id, user=viewer, role="viewer")

    # 1. Queued run cancels immediately
    queued_run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Queued cancellation test",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(queued_run)
    db_session.commit()
    db_session.refresh(queued_run)

    # Viewer cannot cancel (403)
    res_viewer = client.post(
        f"/workspaces/{ws.id}/research/runs/{queued_run.id}/cancel",
        headers=auth_header(viewer),
    )
    assert res_viewer.status_code == 403

    # Outsider cannot access cancel endpoint
    res_outsider = client.post(
        f"/workspaces/{ws.id}/research/runs/{queued_run.id}/cancel",
        headers=auth_header(outsider),
    )
    assert res_outsider.status_code in (403, 404)

    res_cancel_queued = client.post(
        f"/workspaces/{ws.id}/research/runs/{queued_run.id}/cancel",
        headers=auth_header(owner),
    )
    assert res_cancel_queued.status_code == 200
    payload_queued = res_cancel_queued.json()
    assert payload_queued["status"] == "cancelled"
    assert payload_queued["cancel_requested"] is True

    # 2. In-flight run reports cancel_requested=True honestly without faking immediate cancelled status
    inflight_run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="In-flight cancellation test",
        status="synthesizing",
        run_metadata={
            "selected_document_ids": [doc1.id, doc2.id],
            "lifecycle": {
                "worker_id": "worker-active",
                "lease_expires_at": (
                    datetime.now(timezone.utc) + timedelta(minutes=2)
                ).isoformat(),
            },
        },
    )
    db_session.add(inflight_run)
    db_session.commit()
    db_session.refresh(inflight_run)

    res_cancel_inflight = client.post(
        f"/workspaces/{ws.id}/research/runs/{inflight_run.id}/cancel",
        headers=auth_header(owner),
    )
    assert res_cancel_inflight.status_code == 200
    payload_inflight = res_cancel_inflight.json()
    assert payload_inflight["status"] == "synthesizing"
    assert payload_inflight["cancel_requested"] is True

    # 3. Terminal run returns 409 Conflict
    res_cancel_again = client.post(
        f"/workspaces/{ws.id}/research/runs/{queued_run.id}/cancel",
        headers=auth_header(owner),
    )
    assert res_cancel_again.status_code == 409


def test_idempotent_lease_claim_and_abandoned_run_recovery(db_session: Session):
    owner = create_user_fixture(db_session, "owner-recovery@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="lease-recovery"
    )

    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Lease & recovery test",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    # Worker A claims active lease
    claimed_a = claim_research_run(
        db_session,
        run_id=run.id,
        worker_id="worker-A",
        lease_seconds=120,
    )
    assert claimed_a is not None
    assert claimed_a.status == "running"

    # Worker B attempting duplicate execution while Worker A holds lease is rejected
    claimed_b = claim_research_run(
        db_session,
        run_id=run.id,
        worker_id="worker-B",
        lease_seconds=120,
    )
    assert claimed_b is None

    # Simulate worker crash by expiring lease in the past while run is in 'synthesizing'
    expired_ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    meta = dict(claimed_a.run_metadata or {})
    meta["lifecycle"]["lease_expires_at"] = expired_ts
    claimed_a.status = "synthesizing"
    claimed_a.run_metadata = meta
    db_session.commit()

    requeued = recover_abandoned_research_runs(db_session)
    assert run.id in requeued

    db_session.expire_all()
    recovered = db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
    assert recovered.status == "queued"

    # Exhaust max attempts and verify recovery marks run as failed safely
    meta2 = dict(recovered.run_metadata or {})
    meta2["lifecycle"]["attempt_count"] = MAX_RESEARCH_RUN_ATTEMPTS
    meta2["lifecycle"]["lease_expires_at"] = expired_ts
    recovered.status = "validating"
    recovered.run_metadata = meta2
    db_session.commit()

    requeued_after_max = recover_abandoned_research_runs(db_session)
    assert run.id not in requeued_after_max

    db_session.expire_all()
    failed_run = db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
    assert failed_run.status == "failed"
    assert failed_run.run_metadata["lifecycle"]["error_code"] == "RUN_LEASE_EXPIRED"
    assert failed_run.completed_at is not None


def test_lease_heartbeat_renews_during_long_running_synthesis(
    db_session: Session,
):
    owner = create_user_fixture(db_session, "owner-heartbeat@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="heartbeat"
    )
    chunk = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc1.id)
        .first()
    )

    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Long synthesis exceeding initial lease TTL",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    import threading

    _session_lock = threading.Lock()

    class _SharedSessionProxy:
        def __init__(self, session: Session):
            self._session = session
        def query(self, *args, **kwargs):
            return self._session.query(*args, **kwargs)
        def commit(self) -> None:
            self._session.commit()
        def rollback(self) -> None:
            self._session.rollback()
        def close(self) -> None:
            pass

    hb_session_factory = lambda: _SharedSessionProxy(db_session)
    hb_session_factory.lock = _session_lock

    recovery_called_mid_synthesis: list[list[int]] = []

    async def fake_retrieve(db, **kwargs):
        return [
            {
                "document_id": doc1.id,
                "filename": doc1.filename,
                "chunk_id": chunk.id,
                "page_number": 1,
                "score": 0.92,
                "content": chunk.content,
            }
        ]

    async def slow_synthesize(*, query: str, candidates: list[dict]):
        # Sleep longer than the 0.35s lease TTL so heartbeat must renew it
        await asyncio.sleep(0.55)
        with _session_lock:
            requeued = recover_abandoned_research_runs(db_session)
            recovery_called_mid_synthesis.append(requeued)
        await asyncio.sleep(0.25)
        return {
            "answer": "## Findings\nHeartbeat kept lease alive [C1].",
            "facets": {
                "methodology": "Heartbeat test [C1].",
                "datasets": "Synthetic [C1].",
                "metrics": "Lease renewal [C1].",
                "findings": "Heartbeat kept lease alive [C1].",
                "limitations": "None [C1].",
            },
            "citations": [
                {
                    "citation_id": "C1",
                    "document_id": doc1.id,
                    "filename": doc1.filename,
                    "chunk_id": chunk.id,
                    "page_number": 1,
                    "excerpt": chunk.content[:80],
                }
            ],
            "evidence": candidates,
            "provider": "mock",
            "model": "mock-model",
        }

    with (
        patch(
            "app.services.research_execution.retrieve_multi_document_candidates",
            side_effect=fake_retrieve,
        ),
        patch(
            "app.services.research_execution.synthesize_research_answer",
            side_effect=slow_synthesize,
        ),
    ):
        completed = asyncio.run(
            execute_research_run(
                db_session,
                run_id=run.id,
                worker_id="worker-heartbeat-1",
                lease_seconds=0.35,
                heartbeat_interval_seconds=0.1,
                heartbeat_session_factory=hb_session_factory,
            )
        )

    assert completed is not None
    assert completed.status == "completed"
    assert recovery_called_mid_synthesis == [[]]
    lifecycle = (completed.run_metadata or {}).get("lifecycle") or {}
    assert lifecycle.get("lease_renewed_at") is not None


def test_stale_worker_fenced_when_lease_lost_mid_synthesis(
    db_session: Session,
):
    owner = create_user_fixture(db_session, "owner-fence@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="fence"
    )
    chunk = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc1.id)
        .first()
    )

    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Concurrent ownership steal test",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    class _SharedSessionProxy:
        def __init__(self, session: Session):
            self._session = session
        def __getattr__(self, name: str):
            return getattr(self._session, name)
        def close(self) -> None:
            pass

    other_session_factory = lambda: _SharedSessionProxy(db_session)

    async def fake_retrieve(db, **kwargs):
        return [
            {
                "document_id": doc1.id,
                "filename": doc1.filename,
                "chunk_id": chunk.id,
                "page_number": 1,
                "score": 0.90,
                "content": chunk.content,
            }
        ]

    async def hijacked_synthesize(*, query: str, candidates: list[dict]):
        # Simulate Worker A stalling and Worker B reclaiming the run
        other_db = other_session_factory()
        try:
            target = other_db.query(ResearchRun).filter(ResearchRun.id == run.id).first()
            meta = dict(target.run_metadata or {})
            lifecycle = dict(meta.get("lifecycle") or {})
            lifecycle["lease_expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=30)
            ).isoformat()
            meta["lifecycle"] = lifecycle
            target.run_metadata = meta
            other_db.commit()

            requeued = recover_abandoned_research_runs(other_db)
            assert run.id in requeued

            claimed_b = claim_research_run(
                other_db,
                run_id=run.id,
                worker_id="worker-b",
                lease_seconds=120,
            )
            assert claimed_b is not None
        finally:
            other_db.close()

        return {
            "answer": "## Findings\nStale worker output that must NOT commit [C1].",
            "facets": {
                "methodology": "Stale [C1].",
                "datasets": "Stale [C1].",
                "metrics": "Stale [C1].",
                "findings": "Stale [C1].",
                "limitations": "Stale [C1].",
            },
            "citations": [
                {
                    "citation_id": "C1",
                    "document_id": doc1.id,
                    "filename": doc1.filename,
                    "chunk_id": chunk.id,
                    "page_number": 1,
                    "excerpt": chunk.content[:80],
                }
            ],
            "evidence": candidates,
            "provider": "mock",
            "model": "mock-model",
        }

    with (
        patch(
            "app.services.research_execution.retrieve_multi_document_candidates",
            side_effect=fake_retrieve,
        ),
        patch(
            "app.services.research_execution.synthesize_research_answer",
            side_effect=hijacked_synthesize,
        ),
    ):
        execute_research_run_result = asyncio.run(
            execute_research_run(
                db_session,
                run_id=run.id,
                worker_id="worker-a",
                lease_seconds=120,
                heartbeat_interval_seconds=60.0,
            )
        )

    db_session.expire_all()
    fresh = db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
    assert fresh is not None
    assert fresh.status == "running"
    assert fresh.answer is None
    assert ((fresh.run_metadata or {}).get("lifecycle") or {}).get("worker_id") == "worker-b"
    assert execute_research_run_result is not None


def test_transactional_outbox_persists_and_recovers_when_redis_unavailable(
    client: TestClient,
    db_session: Session,
):
    from app.db.models import ResearchRunOutbox
    from app.workers.research_worker import (
        ResearchRunDispatcher,
        reconcile_stranded_queued_runs,
    )

    owner = create_user_fixture(db_session, "owner-outbox@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="outbox"
    )

    with patch(
        "app.api.research.ResearchRunDispatcher.enqueue",
        new=AsyncMock(side_effect=RuntimeError("redis-connection-refused")),
    ):
        res = client.post(
            f"/workspaces/{ws.id}/research/runs?async_mode=true",
            headers=auth_header(owner),
            json={
                "query": "Durable outbox creation test",
                "document_ids": [doc1.id, doc2.id],
            },
        )

    assert res.status_code == 202, res.text
    run_id = res.json()["id"]

    db_session.expire_all()
    outbox = (
        db_session.query(ResearchRunOutbox)
        .filter(ResearchRunOutbox.research_run_id == run_id)
        .first()
    )
    assert outbox is not None
    assert outbox.status == "pending"
    assert outbox.attempts == 1
    assert "redis-connection-refused" in (outbox.last_error or "")

    class _FakeRedis:
        def __init__(self):
            self.added: list[tuple[str, dict]] = []

        async def xgroup_create(self, **kwargs):
            return True

        async def xadd(self, stream, fields):
            self.added.append((stream, fields))
            return "1700000000000-0"

    fake_redis = _FakeRedis()
    published = asyncio.run(
        ResearchRunDispatcher.flush_pending_outbox(db_session, redis=fake_redis)
    )
    assert published == 1
    assert len(fake_redis.added) == 1

    db_session.expire_all()
    refreshed_outbox = (
        db_session.query(ResearchRunOutbox)
        .filter(ResearchRunOutbox.id == outbox.id)
        .first()
    )
    assert refreshed_outbox.status == "published"
    assert refreshed_outbox.published_at is not None

    run = db_session.query(ResearchRun).filter(ResearchRun.id == run_id).first()
    run.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    db_session.commit()
    reconciled = reconcile_stranded_queued_runs(db_session, grace_seconds=5.0)
    assert run_id in reconciled


def test_worker_reclaims_abandoned_pending_messages_via_xautoclaim(
    db_session: Session,
):
    from app.workers.research_worker import (
        RESEARCH_RUN_CONSUMER_GROUP,
        RESEARCH_RUN_PAYLOAD_FIELD,
        RESEARCH_RUN_QUEUE,
        ResearchRunWorker,
    )

    owner = create_user_fixture(db_session, "owner-xautoclaim@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="xautoclaim"
    )
    chunk = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc1.id)
        .first()
    )

    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Pending entry reclamation after worker crash",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    import json

    pending_msg_id = "1700000000001-0"
    pending_fields = {
        RESEARCH_RUN_PAYLOAD_FIELD: json.dumps(
            {"run_id": run.id, "correlation_id": "cid-xautoclaim-1"}
        )
    }

    class _FakeRedisStream:
        def __init__(self):
            self.pending = [(pending_msg_id, pending_fields)]
            self.acked: list[tuple[str, str, str]] = []

        async def xgroup_create(self, **kwargs):
            return True

        async def xautoclaim(
            self,
            *,
            name: str,
            groupname: str,
            consumername: str,
            min_idle_time: int,
            start_id: str,
            count: int,
        ):
            assert name == RESEARCH_RUN_QUEUE
            assert groupname == RESEARCH_RUN_CONSUMER_GROUP
            claimed = list(self.pending)
            self.pending.clear()
            return ("0-0", claimed, [])

        async def xack(self, stream: str, group: str, message_id: str):
            self.acked.append((stream, group, message_id))
            return 1

    class _SharedSessionScope:
        def __enter__(self):
            return db_session

        def __exit__(self, exc_type, exc, tb):
            return False

    async def fake_retrieve(db, **kwargs):
        return [
            {
                "document_id": doc1.id,
                "filename": doc1.filename,
                "chunk_id": chunk.id,
                "page_number": 1,
                "score": 0.95,
                "content": chunk.content,
            }
        ]

    async def fake_synthesize(*, query: str, candidates: list[dict]):
        return {
            "answer": "## Findings\nRecovered via XAUTOCLAIM [C1].",
            "facets": {
                "methodology": "XAUTOCLAIM recovery [C1].",
                "datasets": "Synthetic [C1].",
                "metrics": "Zero lost deliveries [C1].",
                "findings": "Recovered via XAUTOCLAIM [C1].",
                "limitations": "None [C1].",
            },
            "citations": [
                {
                    "citation_id": "C1",
                    "document_id": doc1.id,
                    "filename": doc1.filename,
                    "chunk_id": chunk.id,
                    "page_number": 1,
                    "excerpt": chunk.content[:80],
                }
            ],
            "evidence": candidates,
            "provider": "mock",
            "model": "mock-model",
        }

    fake_redis = _FakeRedisStream()
    worker = ResearchRunWorker(
        worker_id="worker-recovery-2",
        redis=fake_redis,
        pending_idle_ms=1000,
    )

    with (
        patch("app.workers.research_worker.session_scope", return_value=_SharedSessionScope()),
        patch(
            "app.services.research_execution.retrieve_multi_document_candidates",
            side_effect=fake_retrieve,
        ),
        patch(
            "app.services.research_execution.synthesize_research_answer",
            side_effect=fake_synthesize,
        ),
    ):
        reclaimed = asyncio.run(worker.reclaim_abandoned_messages())

    assert reclaimed == 1
    assert fake_redis.acked == [
        (RESEARCH_RUN_QUEUE, RESEARCH_RUN_CONSUMER_GROUP, pending_msg_id)
    ]
    db_session.expire_all()
    finished = db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
    assert finished.status == "completed"
    assert finished.answer is not None


def test_worker_crash_recovery_across_all_stages(
    db_session: Session,
):
    from app.db.models import ResearchRunDocument

    owner = create_user_fixture(db_session, "owner-crash-stages@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="crash-stages"
    )
    chunk = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc1.id)
        .first()
    )

    for stage_to_crash in ("retrieving", "synthesizing", "validating"):
        run = ResearchRun(
            workspace_id=ws.id,
            requester_id=owner.id,
            query=f"Crash recovery test during {stage_to_crash}",
            status="queued",
            run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        crashed = {"done": False}

        async def fake_retrieve(db, **kwargs):
            if stage_to_crash == "retrieving" and not crashed["done"]:
                crashed["done"] = True
                # Simulate hard process crash by leaving expired lease in `retrieving`
                target = db.query(ResearchRun).filter(ResearchRun.id == run.id).first()
                meta = dict(target.run_metadata or {})
                lc = dict(meta.get("lifecycle") or {})
                lc["lease_expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(seconds=60)
                ).isoformat()
                meta["lifecycle"] = lc
                target.run_metadata = meta
                db.commit()
                raise RuntimeError("simulated-worker-sigkill-during-retrieving")
            return [
                {
                    "document_id": doc1.id,
                    "filename": doc1.filename,
                    "chunk_id": chunk.id,
                    "page_number": 1,
                    "score": 0.93,
                    "content": chunk.content,
                }
            ]

        async def fake_synthesize(*, query: str, candidates: list[dict]):
            if stage_to_crash == "synthesizing" and not crashed["done"]:
                crashed["done"] = True
                target = (
                    db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
                )
                meta = dict(target.run_metadata or {})
                lc = dict(meta.get("lifecycle") or {})
                lc["lease_expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(seconds=60)
                ).isoformat()
                meta["lifecycle"] = lc
                target.run_metadata = meta
                db_session.commit()
                raise RuntimeError("simulated-worker-sigkill-during-synthesizing")
            return {
                "answer": f"## Findings\nRecovered after crash in {stage_to_crash} [C1].",
                "facets": {
                    "methodology": "Crash test [C1].",
                    "datasets": "Synthetic [C1].",
                    "metrics": "Stage durability [C1].",
                    "findings": f"Recovered after crash in {stage_to_crash} [C1].",
                    "limitations": "None [C1].",
                },
                "citations": [
                    {
                        "citation_id": "C1",
                        "document_id": doc1.id,
                        "filename": doc1.filename,
                        "chunk_id": chunk.id,
                        "page_number": 1,
                        "excerpt": chunk.content[:80],
                    }
                ],
                "evidence": candidates,
                "provider": "mock",
                "model": "mock-model",
            }

        def fake_persist(db, *, run, document_ids, candidates, citations):
            if stage_to_crash == "validating" and not crashed["done"]:
                crashed["done"] = True
                # Insert partial provenance row to verify idempotent cleanup on retry
                db.add(
                    ResearchRunDocument(
                        research_run_id=run.id,
                        document_id=doc1.id,
                        provenance={"partial": True},
                    )
                )
                meta = dict(run.run_metadata or {})
                lc = dict(meta.get("lifecycle") or {})
                lc["lease_expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(seconds=60)
                ).isoformat()
                meta["lifecycle"] = lc
                run.run_metadata = meta
                db.commit()
                raise RuntimeError("simulated-worker-sigkill-during-validating")
            from app.services.research_execution import _ORIG_PERSIST

            return _ORIG_PERSIST(
                db,
                run=run,
                document_ids=document_ids,
                candidates=candidates,
                citations=citations,
            )

        with (
            patch(
                "app.services.research_execution.retrieve_multi_document_candidates",
                side_effect=fake_retrieve,
            ),
            patch(
                "app.services.research_execution.synthesize_research_answer",
                side_effect=fake_synthesize,
            ),
            patch(
                "app.services.research_execution.persist_document_provenance",
                side_effect=fake_persist,
            ),
        ):
            # Attempt 1 crashes and marks failed/expired; reset status to the crashed stage
            # to simulate SIGKILL before _finalize_failed could run
            asyncio.run(
                execute_research_run(
                    db_session,
                    run_id=run.id,
                    worker_id="crashed-worker-1",
                )
            )
            row = db_session.query(ResearchRun).filter(ResearchRun.id == run.id).first()
            row.status = stage_to_crash
            row.completed_at = None
            row.error_message = None
            meta = dict(row.run_metadata or {})
            lc = dict(meta.get("lifecycle") or {})
            lc["lease_expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=60)
            ).isoformat()
            meta["lifecycle"] = lc
            row.run_metadata = meta
            db_session.commit()

            requeued = recover_abandoned_research_runs(db_session)
            assert run.id in requeued

            # Attempt 2 recovers cleanly and replaces any partial provenance
            recovered = asyncio.run(
                execute_research_run(
                    db_session,
                    run_id=run.id,
                    worker_id="healthy-worker-2",
                )
            )

        assert recovered is not None
        assert recovered.status == "completed"
        prov_rows = (
            db_session.query(ResearchRunDocument)
            .filter(ResearchRunDocument.research_run_id == run.id)
            .all()
        )
        assert len(prov_rows) == 2


def test_worker_graceful_shutdown_drains_and_leaves_unfinished_unacked():
    from app.workers.research_worker import (
        RESEARCH_RUN_CONSUMER_GROUP,
        RESEARCH_RUN_PAYLOAD_FIELD,
        RESEARCH_RUN_QUEUE,
        ResearchRunWorker,
    )
    import json

    class _FakeRedis:
        def __init__(self):
            self.acked: list[str] = []

        async def xack(self, stream: str, group: str, message_id: str):
            assert stream == RESEARCH_RUN_QUEUE
            assert group == RESEARCH_RUN_CONSUMER_GROUP
            self.acked.append(message_id)
            return 1

    fake_redis = _FakeRedis()
    worker = ResearchRunWorker(
        worker_id="worker-shutdown-test",
        redis=fake_redis,
        concurrency=2,
        shutdown_grace_seconds=0.25,
    )

    async def fake_execute(db, *, run_id: int, **kwargs):
        if run_id == 101:
            # Completes inside the 0.25s grace period
            await asyncio.sleep(0.05)
            return None
        # Exceeds the 0.25s grace period and must be cancelled without XACK
        await asyncio.sleep(2.0)
        return None

    class _NoopScope:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    async def _exercise_shutdown():
        with (
            patch("app.workers.research_worker.session_scope", return_value=_NoopScope()),
            patch("app.workers.research_worker.execute_research_run", side_effect=fake_execute),
        ):
            worker.spawn_message_task(
                "1700000000101-0",
                {RESEARCH_RUN_PAYLOAD_FIELD: json.dumps({"run_id": 101})},
            )
            worker.spawn_message_task(
                "1700000000102-0",
                {RESEARCH_RUN_PAYLOAD_FIELD: json.dumps({"run_id": 102})},
            )
            await asyncio.sleep(0.01)
            assert len(worker._active_tasks) == 2
            summary = await worker.shutdown(timeout=0.25)
            assert summary == {"drained": 1, "cancelled": 1}
            assert len(worker._active_tasks) == 0

    asyncio.run(_exercise_shutdown())
    assert fake_redis.acked == ["1700000000101-0"]

def test_same_worker_cannot_claim_active_run_twice(db_session: Session):
    from app.services.research_execution import claim_research_run

    owner = create_user_fixture(db_session, "same-worker-claim@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="same-worker-claim"
    )
    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Duplicate delivery for same worker",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    first = claim_research_run(db_session, run_id=run.id, worker_id="worker-shared")
    second = claim_research_run(db_session, run_id=run.id, worker_id="worker-shared")

    assert first is not None
    assert second is None
    first_lc = (first.run_metadata or {}).get("lifecycle") or {}
    assert first_lc.get("worker_id") == "worker-shared"
    assert first_lc.get("lease_token")


def test_superseded_lease_token_cannot_advance_or_finalize(db_session: Session):
    from app.services.research_execution import (
        ResearchRunOwnershipLostError,
        _finalize_failed,
        _lock_owned_run,
        claim_research_run,
    )

    owner = create_user_fixture(db_session, "lease-fencing@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="lease-fencing"
    )
    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Lease token fencing",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    first = claim_research_run(
        db_session, run_id=run.id, worker_id="worker-same", lease_seconds=0.01
    )
    assert first is not None
    old_token = ((first.run_metadata or {}).get("lifecycle") or {}).get("lease_token")
    assert old_token

    lc = dict((run.run_metadata or {}).get("lifecycle") or {})
    lc["lease_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    run.run_metadata = {**(run.run_metadata or {}), "lifecycle": lc}
    db_session.commit()

    second = claim_research_run(
        db_session, run_id=run.id, worker_id="worker-same", lease_seconds=60.0
    )
    assert second is not None
    new_token = ((second.run_metadata or {}).get("lifecycle") or {}).get("lease_token")
    assert new_token and new_token != old_token

    with pytest.raises(ResearchRunOwnershipLostError):
        _lock_owned_run(
            db_session, run_id=run.id, worker_id="worker-same", lease_token=old_token
        )

    with pytest.raises(ResearchRunOwnershipLostError):
        _finalize_failed(
            db_session,
            run_id=run.id,
            workspace_id=ws.id,
            worker_id="worker-same",
            lease_token=old_token,
            error_message="stale failure",
            error_code="STALE_WORKER",
            correlation_id=None,
        )


def test_old_lease_token_cannot_renew_new_execution_lease(db_session: Session):
    from app.services.research_execution import (
        claim_research_run,
        renew_research_run_lease,
    )

    owner = create_user_fixture(db_session, "heartbeat-fencing@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="heartbeat-fencing"
    )
    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Heartbeat fencing",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    old_claim = claim_research_run(
        db_session, run_id=run.id, worker_id="worker-hb", lease_seconds=0.01
    )
    assert old_claim is not None
    old_token = ((old_claim.run_metadata or {}).get("lifecycle") or {}).get("lease_token")

    run.status = "retrieving"
    lc = dict((run.run_metadata or {}).get("lifecycle") or {})
    lc["lease_expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    run.run_metadata = {**(run.run_metadata or {}), "lifecycle": lc}
    db_session.commit()

    new_claim = claim_research_run(
        db_session, run_id=run.id, worker_id="worker-hb", lease_seconds=120.0
    )
    assert new_claim is not None
    new_expiry = ((new_claim.run_metadata or {}).get("lifecycle") or {}).get("lease_expires_at")

    renewed = renew_research_run_lease(
        db_session,
        run_id=run.id,
        worker_id="worker-hb",
        lease_token=old_token,
        lease_seconds=300.0,
    )
    assert renewed is False
    db_session.refresh(run)
    assert ((run.run_metadata or {}).get("lifecycle") or {}).get("lease_expires_at") == new_expiry


def test_duplicate_outbox_delivery_starts_only_one_execution(db_session: Session):
    from app.services.research_execution import claim_research_run

    owner = create_user_fixture(db_session, "duplicate-delivery@phase3a.test")
    ws, doc1, doc2 = _seed_workspace_with_two_docs(
        db_session, owner=owner, prefix="duplicate-delivery"
    )
    run = ResearchRun(
        workspace_id=ws.id,
        requester_id=owner.id,
        query="Duplicate outbox delivery",
        status="queued",
        run_metadata={"selected_document_ids": [doc1.id, doc2.id]},
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    first_started = asyncio.Event()
    allow_first_to_finish = asyncio.Event()
    retrieve_calls = 0
    synthesize_calls = 0

    async def _run_both_claims():
        nonlocal retrieve_calls, synthesize_calls

        async def fake_retrieve(db, **kwargs):
            nonlocal retrieve_calls
            retrieve_calls += 1
            first_started.set()
            await allow_first_to_finish.wait()
            raise RuntimeError("stop after verifying exclusive claim")

        async def fake_synthesize(db, **kwargs):
            nonlocal synthesize_calls
            synthesize_calls += 1
            return "unused"

        c1 = claim_research_run(db_session, run_id=run.id, worker_id="worker-dup")
        c2 = claim_research_run(db_session, run_id=run.id, worker_id="worker-dup")
        assert c1 is not None
        assert c2 is None

        task1 = asyncio.create_task(fake_retrieve(db_session))
        await first_started.wait()
        # Duplicate delivery arrives while task1 holds active lease
        assert claim_research_run(db_session, run_id=run.id, worker_id="worker-dup") is None
        allow_first_to_finish.set()
        with pytest.raises(RuntimeError, match="stop after verifying exclusive claim"):
            await task1
        _ = fake_synthesize

    asyncio.run(_run_both_claims())
    assert retrieve_calls == 1
    assert synthesize_calls == 0
