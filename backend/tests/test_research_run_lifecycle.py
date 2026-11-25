from __future__ import annotations

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
