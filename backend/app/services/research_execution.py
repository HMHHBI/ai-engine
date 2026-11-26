from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import correlation_id_var
from app.db.models import (
    Document,
    ResearchRun,
    ResearchRunDocument,
    WorkspaceDocument)
from app.db.session import session_scope
from app.schemas.research_schema import (
    ACTIVE_RESEARCH_STATUSES,
    TERMINAL_RESEARCH_STATUSES)
from app.services.multi_doc_retrieval import (
    DocumentSelectionError,
    retrieve_multi_document_candidates)
from app.services.research_synthesis import (
    SynthesisValidationError,
    synthesize_research_answer)

logger = logging.getLogger(__name__)

RESEARCH_RUN_LEASE_SECONDS = 120
MAX_RESEARCH_RUN_ATTEMPTS = 2

STAGE_PROGRESS: dict[str, int] = {
    "queued": 0,
    "running": 10,
    "retrieving": 25,
    "synthesizing": 60,
    "validating": 85,
    "completed": 100,
    "failed": 100,
    "cancelled": 100,
}


class ResearchRunTerminalError(ValueError):
    """Raised when attempting an invalid transition on a terminal research run."""


class ResearchRunOwnershipLostError(RuntimeError):
    """Raised when a worker loses its lease ownership to recovery or another worker."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def get_lifecycle_snapshot(run: ResearchRun) -> dict[str, Any]:
    meta = run.run_metadata or {}
    lifecycle = dict(meta.get("lifecycle") or {})
    status = run.status
    return {
        "run_id": run.id,
        "workspace_id": run.workspace_id,
        "status": status,
        "stage": status,
        "progress_percent": STAGE_PROGRESS.get(status, 0),
        "cancel_requested": bool(lifecycle.get("cancel_requested", False)),
        "attempt_count": int(lifecycle.get("attempt_count", 0)),
        "correlation_id": lifecycle.get("correlation_id"),
        "stage_timestamps": dict(lifecycle.get("stage_timestamps") or {}),
        "error_code": lifecycle.get("error_code"),
        "error_message": run.error_message,
        "updated_at": (
            run.completed_at.isoformat()
            if run.completed_at is not None
            else (
                lifecycle.get("updated_at")
                or (run.created_at.isoformat() if run.created_at else _utc_now().isoformat())
            )
        ),
    }


def _update_lifecycle(
    run: ResearchRun,
    *,
    status: str | None = None,
    worker_id: str | None = None,
    lease_seconds: float | None = RESEARCH_RUN_LEASE_SECONDS,
    correlation_id: str | None = None,
    error_code: str | None = None,
    increment_attempt: bool = False,
    clear_lease: bool = False) -> None:
    now = _utc_now()
    now_iso = now.isoformat()
    meta = dict(run.run_metadata or {})
    lifecycle = dict(meta.get("lifecycle") or {})
    timestamps = dict(lifecycle.get("stage_timestamps") or {})

    if status is not None:
        run.status = status
        timestamps[status] = now_iso

    if correlation_id:
        lifecycle["correlation_id"] = correlation_id
    elif not lifecycle.get("correlation_id"):
        cid = correlation_id_var.get()
        if cid:
            lifecycle["correlation_id"] = cid

    if worker_id is not None:
        lifecycle["worker_id"] = worker_id

    if increment_attempt:
        lifecycle["attempt_count"] = int(lifecycle.get("attempt_count", 0)) + 1

    if clear_lease:
        lifecycle["lease_expires_at"] = None
        lifecycle["worker_id"] = None
        lifecycle["lease_token"] = None
    elif lease_seconds is not None:
        lifecycle["lease_expires_at"] = (
            now + timedelta(seconds=float(lease_seconds))
        ).isoformat()

    if error_code is not None:
        lifecycle["error_code"] = error_code

    lifecycle["stage_timestamps"] = timestamps
    lifecycle["updated_at"] = now_iso
    meta["lifecycle"] = lifecycle
    run.run_metadata = meta


def _is_cancel_requested(db: Session, run_id: int) -> bool:
    row = (
        db.query(ResearchRun.status, ResearchRun.run_metadata)
        .filter(ResearchRun.id == run_id)
        .first()
    )
    if row is None:
        return True
    status_val, meta = row
    if status_val == "cancelled":
        return True
    lifecycle = (meta or {}).get("lifecycle") or {}
    return bool(lifecycle.get("cancel_requested", False))


def renew_research_run_lease(
    db: Session,
    *,
    run_id: int,
    worker_id: str,
    lease_token: str | None = None,
    lease_seconds: float = RESEARCH_RUN_LEASE_SECONDS) -> bool:
    """
    Conditionally renew an active research run lease iff `worker_id` (and
    `lease_token` when provided) still owns it and the run has not entered a
    terminal or queued state.
    """
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.status.in_(tuple(ACTIVE_RESEARCH_STATUSES - {"queued"})))
        .with_for_update()
        .first()
    )
    if run is None:
        return False

    meta = dict(run.run_metadata or {})
    lifecycle = dict(meta.get("lifecycle") or {})
    if lifecycle.get("worker_id") != worker_id:
        return False
    if lease_token is not None and lifecycle.get("lease_token") != lease_token:
        return False

    now = _utc_now()
    now_iso = now.isoformat()
    lifecycle["lease_expires_at"] = (
        now + timedelta(seconds=float(lease_seconds))
    ).isoformat()
    lifecycle["lease_renewed_at"] = now_iso
    lifecycle["updated_at"] = now_iso
    meta["lifecycle"] = lifecycle
    run.run_metadata = meta
    db.commit()
    return True


def _lock_owned_run(
    db: Session,
    *,
    run_id: int,
    worker_id: str,
    lease_token: str | None = None) -> ResearchRun:
    """
    Acquire row lock and verify that `worker_id` (and `lease_token` when
    provided) still owns the non-terminal run.
    Raises ResearchRunOwnershipLostError if another execution claimed the run.
    """
    run = (
        db.query(ResearchRun)
        .filter(ResearchRun.id == run_id)
        .with_for_update()
        .first()
    )
    if run is None or run.status in TERMINAL_RESEARCH_STATUSES:
        raise ResearchRunOwnershipLostError(
            f"Research run {run_id} is no longer active."
        )
    lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})
    if lifecycle.get("worker_id") != worker_id:
        raise ResearchRunOwnershipLostError(
            f"Worker {worker_id} lost lease ownership of research run {run_id}."
        )
    if lease_token is not None and lifecycle.get("lease_token") != lease_token:
        raise ResearchRunOwnershipLostError(
            f"Execution lease for research run {run_id} has been superseded."
        )
    return run


def claim_research_run(
    db: Session,
    *,
    run_id: int,
    worker_id: str,
    lease_seconds: float = RESEARCH_RUN_LEASE_SECONDS,
    correlation_id: str | None = None) -> ResearchRun | None:
    """
    Atomically claim a non-terminal research run if unleased or if its lease expired.
    Prevents duplicate execution across concurrent workers/requests.
    """
    run = (
        db.query(ResearchRun)
        .filter(ResearchRun.id == run_id)
        .with_for_update()
        .first()
    )
    if run is None or run.status in TERMINAL_RESEARCH_STATUSES:
        return None

    now = _utc_now()
    lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})

    if lifecycle.get("cancel_requested"):
        _update_lifecycle(
            run,
            status="cancelled",
            correlation_id=correlation_id,
            clear_lease=True)
        run.completed_at = now
        db.commit()
        return None

    current_owner = lifecycle.get("worker_id")
    lease_expires = _parse_iso(lifecycle.get("lease_expires_at"))

    if (
        current_owner

        and lease_expires is not None
        and lease_expires > now
    ):
        # Active lease owned by another worker
        return None

    attempt_count = int(lifecycle.get("attempt_count", 0))
    if attempt_count >= MAX_RESEARCH_RUN_ATTEMPTS:
        _update_lifecycle(
            run,
            status="failed",
            correlation_id=correlation_id,
            error_code="MAX_ATTEMPTS_EXCEEDED",
            clear_lease=True)
        run.error_message = "Research synthesis exceeded maximum recovery attempts."
        run.completed_at = now
        db.commit()
        return None

    _update_lifecycle(
        run,
        status="running",
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        correlation_id=correlation_id,
        increment_attempt=True)
    lease_token = uuid.uuid4().hex
    lifecycle["lease_token"] = lease_token
    meta = dict(run.run_metadata or {})
    meta["lifecycle"] = lifecycle
    run.run_metadata = meta
    db.commit()
    db.refresh(run)
    return run


def request_research_run_cancellation(
    db: Session,
    *,
    workspace_id: int,
    run_id: int) -> tuple[ResearchRun, bool]:
    """
    Cancel a queued run immediately or mark an in-flight run for cooperative cancellation.
    Raises ResearchRunTerminalError if already completed/failed/cancelled.
    """
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id)
        .with_for_update()
        .first()
    )
    if run is None:
        raise LookupError("Research run not found.")

    if run.status in TERMINAL_RESEARCH_STATUSES:
        raise ResearchRunTerminalError(
            f"Cannot cancel research run in '{run.status}' state."
        )

    now = _utc_now()
    meta = dict(run.run_metadata or {})
    lifecycle = dict(meta.get("lifecycle") or {})
    lifecycle["cancel_requested"] = True
    lifecycle["cancel_requested_at"] = now.isoformat()
    lifecycle["updated_at"] = now.isoformat()
    meta["lifecycle"] = lifecycle
    run.run_metadata = meta

    if run.status == "queued":
        _update_lifecycle(run, status="cancelled", clear_lease=True)
        run.error_message = "Cancelled by user before execution started."
        run.completed_at = now
        db.commit()
        db.refresh(run)
        return run, True

    # In-flight stage: preserve honest status while signalling cooperative cancellation
    db.commit()
    db.refresh(run)
    return run, True


def recover_abandoned_research_runs(db: Session) -> list[int]:
    """
    Re-queue or fail active research runs whose worker lease has expired.
    Returns IDs of runs re-queued for execution.
    """
    now = _utc_now()
    active_runs = (
        db.query(ResearchRun)
        .filter(ResearchRun.status.in_(tuple(ACTIVE_RESEARCH_STATUSES)))
        .all()
    )

    requeued_ids: list[int] = []
    for run in active_runs:
        if run.status == "queued":
            continue
        lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})
        lease_expires = _parse_iso(lifecycle.get("lease_expires_at"))
        if lease_expires is None or lease_expires > now:
            continue

        locked = (
            db.query(ResearchRun)
            .filter(
                ResearchRun.id == run.id,
                ResearchRun.status.in_(tuple(ACTIVE_RESEARCH_STATUSES)))
            .with_for_update()
            .first()
        )
        if locked is None or locked.status in TERMINAL_RESEARCH_STATUSES:
            continue

        locked_lifecycle = dict((locked.run_metadata or {}).get("lifecycle") or {})
        locked_expires = _parse_iso(locked_lifecycle.get("lease_expires_at"))
        if locked_expires is None or locked_expires > now:
            continue

        if locked_lifecycle.get("cancel_requested"):
            _update_lifecycle(locked, status="cancelled", clear_lease=True)
            locked.error_message = "Cancelled during recovery."
            locked.completed_at = now
            db.commit()
            continue

        attempts = int(locked_lifecycle.get("attempt_count", 0))
        if attempts < MAX_RESEARCH_RUN_ATTEMPTS:
            locked_lifecycle["recovered_at"] = now.isoformat()
            if locked_lifecycle.get("worker_id"):
                locked_lifecycle["last_lost_worker_id"] = locked_lifecycle["worker_id"]
            meta = dict(locked.run_metadata or {})
            meta["lifecycle"] = locked_lifecycle
            locked.run_metadata = meta
            _update_lifecycle(locked, status="queued", clear_lease=True)
            db.commit()
            requeued_ids.append(locked.id)
        else:
            _update_lifecycle(
                locked,
                status="failed",
                error_code="RUN_LEASE_EXPIRED",
                clear_lease=True)
            locked.error_message = (
                "Research run lease expired after worker interruption."
            )
            locked.completed_at = now
            db.commit()

    return requeued_ids


def persist_document_provenance(
    db: Session,
    *,
    run: ResearchRun,
    document_ids: list[int],
    candidates: list[dict[str, Any]],
    citations: list[dict[str, Any]]) -> None:
    # Idempotency guard: clear any partial provenance rows from an interrupted attempt
    db.query(ResearchRunDocument).filter(
        ResearchRunDocument.research_run_id == run.id
    ).delete(synchronize_session=False)

    citations_by_document: dict[int, list[dict[str, Any]]] = {
        document_id: [] for document_id in document_ids
    }
    for citation in citations:
        citations_by_document.setdefault(int(citation["document_id"]), []).append(citation)

    chunks_by_document: dict[int, list[dict[str, Any]]] = {
        document_id: [] for document_id in document_ids
    }
    for candidate in candidates:
        document_id = int(candidate["document_id"])
        chunks_by_document.setdefault(document_id, []).append(
            {
                "chunk_id": int(candidate["chunk_id"]),
                "page_number": candidate.get("page_number"),
                "score": float(candidate.get("score", 0.0)),
            }
        )

    documents = (
        db.query(Document)
        .join(WorkspaceDocument, WorkspaceDocument.document_id == Document.id)
        .filter(
            WorkspaceDocument.workspace_id == run.workspace_id,
            Document.id.in_(document_ids))
        .all()
    )
    documents_by_id = {document.id: document for document in documents}

    if set(documents_by_id) != set(document_ids):
        raise DocumentSelectionError(
            "The selected document association changed during research execution."
        )

    for document_id in document_ids:
        db.add(
            ResearchRunDocument(
                research_run_id=run.id,
                document_id=document_id,
                provenance={
                    "filename": documents_by_id[document_id].filename,
                    "candidate_chunks": chunks_by_document.get(document_id, []),
                    "citations": citations_by_document.get(document_id, []),
                })
        )


def _finalize_cancelled(
    db: Session,
    *,
    run_id: int,
    workspace_id: int,
    worker_id: str,
    correlation_id: str | None,
    lease_token: str | None = None) -> ResearchRun | None:
    db.rollback()
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id)
        .with_for_update()
        .first()
    )
    if run is None:
        return None
    lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})

    if run.status in TERMINAL_RESEARCH_STATUSES:
        return run
    if lifecycle.get("worker_id") != worker_id:
        raise ResearchRunOwnershipLostError(
            f"Worker {worker_id} lost lease ownership of research run {run_id}."
        )
    if lease_token is not None and lifecycle.get("lease_token") != lease_token:
        raise ResearchRunOwnershipLostError(
            f"Execution lease for research run {run_id} has been superseded."
        )
    _update_lifecycle(
        run,
        status="cancelled",
        correlation_id=correlation_id,
        clear_lease=True)
    run.error_message = "Cancelled by user."
    run.completed_at = _utc_now()
    db.commit()
    db.refresh(run)
    return run


def _finalize_failed(
    db: Session,
    *,
    run_id: int,
    workspace_id: int,
    worker_id: str,
    error_message: str,
    error_code: str,
    correlation_id: str | None,
    lease_token: str | None = None) -> ResearchRun | None:
    db.rollback()
    run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id)
        .with_for_update()
        .first()
    )
    if run is None:
        return None
    lifecycle = dict((run.run_metadata or {}).get("lifecycle") or {})

    if run.status in TERMINAL_RESEARCH_STATUSES:
        return run
    if lifecycle.get("worker_id") != worker_id:
        raise ResearchRunOwnershipLostError(
            f"Worker {worker_id} lost lease ownership of research run {run_id}."
        )
    if lease_token is not None and lifecycle.get("lease_token") != lease_token:
        raise ResearchRunOwnershipLostError(
            f"Execution lease for research run {run_id} has been superseded."
        )
    _update_lifecycle(
        run,
        status="failed",
        correlation_id=correlation_id,
        error_code=error_code,
        clear_lease=True)
    run.error_message = error_message[:1000]
    run.completed_at = _utc_now()
    db.commit()
    db.refresh(run)
    return run


async def _lease_heartbeat_loop(
    *,
    run_id: int,
    worker_id: str,
    lease_seconds: float,
    interval_seconds: float,
    ownership_lost: asyncio.Event,
    session_factory: Any = None) -> None:
    while not ownership_lost.is_set():
        await asyncio.sleep(interval_seconds)
        if ownership_lost.is_set():
            break
        try:
            def _renew() -> bool:
                if session_factory is not None:
                    lock = getattr(session_factory, "lock", None)
                    if lock is not None:
                        lock.acquire()
                    try:
                        hb_db = session_factory()
                        try:
                            return renew_research_run_lease(
                                hb_db,
                                run_id=run_id,
                                worker_id=worker_id,
                                lease_seconds=lease_seconds)
                        finally:
                            hb_db.close()
                    finally:
                        if lock is not None:
                            lock.release()
                with session_scope() as hb_db:
                    return renew_research_run_lease(
                        hb_db,
                        run_id=run_id,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds)

            renewed = await asyncio.to_thread(_renew)
            if not renewed:
                ownership_lost.set()
                logger.warning(
                    "research_run_lease_lost_in_heartbeat",
                    extra={
                        "event": "research_run_lease_lost_in_heartbeat",
                        "run_id": run_id,
                        "worker_id": worker_id,
                    })
                break
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception(
                "research_run_lease_heartbeat_error",
                extra={"run_id": run_id, "worker_id": worker_id})


async def execute_research_run(
    db: Session,
    *,
    run_id: int,
    worker_id: str | None = None,
    correlation_id: str | None = None,
    raise_on_error: bool = False,
    lease_seconds: float = RESEARCH_RUN_LEASE_SECONDS,
    heartbeat_interval_seconds: float | None = None,
    heartbeat_session_factory: Any = None) -> ResearchRun | None:
    """
    Execute a research run through durable, stage-persisted transitions:
    queued -> running -> retrieving -> synthesizing -> validating -> completed|failed|cancelled.
    Maintains a periodic lease heartbeat and fences stale workers if lease ownership changes.
    """
    effective_worker = worker_id or f"inline-{uuid.uuid4().hex[:8]}"
    effective_cid = correlation_id or correlation_id_var.get()
    effective_heartbeat = (
        heartbeat_interval_seconds
        if heartbeat_interval_seconds is not None
        else max(1.0, float(lease_seconds) / 3.0)
    )

    claimed = claim_research_run(
        db,
        run_id=run_id,
        worker_id=effective_worker,
        lease_seconds=lease_seconds,
        correlation_id=effective_cid)
    if claimed is None:
        return db.query(ResearchRun).filter(ResearchRun.id == run_id).first()

    claimed_lifecycle = dict((claimed.run_metadata or {}).get("lifecycle") or {})
    lease_token = claimed_lifecycle.get("lease_token")
    if not lease_token:
        raise ResearchRunOwnershipLostError(
            f"Research run {run_id} was claimed without an execution lease token."
        )

    workspace_id = claimed.workspace_id
    requester_id = claimed.requester_id
    query_text = claimed.query
    document_ids = [
        int(doc_id)
        for doc_id in ((claimed.run_metadata or {}).get("selected_document_ids") or [])
    ]

    ownership_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _lease_heartbeat_loop(
            run_id=run_id,
            worker_id=effective_worker,
            lease_seconds=lease_seconds,
            interval_seconds=effective_heartbeat,
            ownership_lost=ownership_lost,
            session_factory=heartbeat_session_factory)
    )

    try:
        # Stage 1: Retrieving
        if _is_cancel_requested(db, run_id):
            return _finalize_cancelled(
                db,
                run_id=run_id,
                workspace_id=workspace_id,
                worker_id=effective_worker, lease_token=lease_token,
                correlation_id=effective_cid)

        locked_run = _lock_owned_run(db, run_id=run_id, worker_id=effective_worker, lease_token=lease_token)
        _update_lifecycle(
            locked_run,
            status="retrieving",
            worker_id=effective_worker,
            lease_seconds=lease_seconds,
            correlation_id=effective_cid)
        db.commit()

        import app.api.research as _research_api

        _api_retrieve = getattr(
            _research_api, "retrieve_multi_document_candidates", _ORIG_RETRIEVE
        )
        _retrieve_fn = (
            _api_retrieve
            if _api_retrieve is not _ORIG_RETRIEVE
            else retrieve_multi_document_candidates
        )
        candidates = await _retrieve_fn(
            db,
            workspace_id=workspace_id,
            requester_id=requester_id,
            document_ids=document_ids,
            query=query_text,
            candidate_limit=40)

        # Stage 2: Synthesizing
        if ownership_lost.is_set():
            raise ResearchRunOwnershipLostError(
                f"Worker {effective_worker} lost lease ownership during retrieval."
            )
        if _is_cancel_requested(db, run_id):
            return _finalize_cancelled(
                db,
                run_id=run_id,
                workspace_id=workspace_id,
                worker_id=effective_worker, lease_token=lease_token,
                correlation_id=effective_cid)

        locked_run = _lock_owned_run(db, run_id=run_id, worker_id=effective_worker, lease_token=lease_token)
        _update_lifecycle(
            locked_run,
            status="synthesizing",
            worker_id=effective_worker,
            lease_seconds=lease_seconds,
            correlation_id=effective_cid)
        db.commit()

        _api_synth = getattr(
            _research_api, "synthesize_research_answer", _ORIG_SYNTH
        )
        _synth_fn = (
            _api_synth
            if _api_synth is not _ORIG_SYNTH
            else synthesize_research_answer
        )
        result = await _synth_fn(
            query=query_text,
            candidates=candidates)

        # Stage 3: Validating & Persisting Provenance
        if ownership_lost.is_set():
            raise ResearchRunOwnershipLostError(
                f"Worker {effective_worker} lost lease ownership during synthesis."
            )
        if _is_cancel_requested(db, run_id):
            return _finalize_cancelled(
                db,
                run_id=run_id,
                workspace_id=workspace_id,
                worker_id=effective_worker, lease_token=lease_token,
                correlation_id=effective_cid)

        locked_run = _lock_owned_run(db, run_id=run_id, worker_id=effective_worker, lease_token=lease_token)
        _update_lifecycle(
            locked_run,
            status="validating",
            worker_id=effective_worker,
            lease_seconds=lease_seconds,
            correlation_id=effective_cid)
        db.commit()

        # Final atomic fenced commit of provenance + answer + completed status
        locked_run = _lock_owned_run(db, run_id=run_id, worker_id=effective_worker, lease_token=lease_token)
        citation_payloads = result["citations"]
        _api_persist = getattr(
            _research_api, "_persist_document_provenance", _ORIG_PERSIST
        )
        _persist_fn = (
            _api_persist
            if _api_persist is not _ORIG_PERSIST
            else persist_document_provenance
        )
        _persist_fn(
            db,
            run=locked_run,
            document_ids=document_ids,
            candidates=result["evidence"],
            citations=citation_payloads)

        if _is_cancel_requested(db, run_id):
            return _finalize_cancelled(
                db,
                run_id=run_id,
                workspace_id=workspace_id,
                worker_id=effective_worker, lease_token=lease_token,
                correlation_id=effective_cid)

        locked_run.answer = {
            "answer": result["answer"],
            "citations": citation_payloads,
            "facets": result.get("facets"),
        }
        locked_run.run_metadata = {
            **(locked_run.run_metadata or {}),
            "provider": result["provider"],
            "model": result["model"],
            "candidate_count": len(result["evidence"]),
            "citation_count": len(citation_payloads),
            "completed_document_ids": sorted(
                {int(candidate["document_id"]) for candidate in result["evidence"]}
            ),
        }
        _update_lifecycle(
            locked_run,
            status="completed",
            correlation_id=effective_cid,
            clear_lease=True)
        locked_run.error_message = None
        locked_run.completed_at = _utc_now()

        db.commit()
        db.refresh(locked_run)
        return locked_run

    except ResearchRunOwnershipLostError:
        db.rollback()
        logger.warning(
            "research_run_stale_worker_fenced",
            extra={
                "event": "research_run_stale_worker_fenced",
                "run_id": run_id,
                "workspace_id": workspace_id,
                "worker_id": effective_worker,
                "correlation_id": effective_cid,
            })
        return db.query(ResearchRun).filter(ResearchRun.id == run_id).first()

    except DocumentSelectionError as exc:
        _finalize_failed(
            db,
            run_id=run_id,
            workspace_id=workspace_id,
            worker_id=effective_worker, lease_token=lease_token,
            error_message=str(exc),
            error_code="INVALID_DOCUMENT_SELECTION",
            correlation_id=effective_cid)
        if raise_on_error:
            raise
        return db.query(ResearchRun).filter(ResearchRun.id == run_id).first()

    except (SynthesisValidationError, ValueError) as exc:
        _finalize_failed(
            db,
            run_id=run_id,
            workspace_id=workspace_id,
            worker_id=effective_worker, lease_token=lease_token,
            error_message=str(exc),
            error_code="SYNTHESIS_VALIDATION_FAILED",
            correlation_id=effective_cid)
        if raise_on_error:
            raise
        return db.query(ResearchRun).filter(ResearchRun.id == run_id).first()

    except Exception:
        logger.exception(
            "research_run_execution_failed",
            extra={
                "event": "research_run_execution_failed",
                "run_id": run_id,
                "workspace_id": workspace_id,
                "correlation_id": effective_cid,
            })
        _finalize_failed(
            db,
            run_id=run_id,
            workspace_id=workspace_id,
            worker_id=effective_worker, lease_token=lease_token,
            error_message="Research synthesis failed.",
            error_code="RESEARCH_SYNTHESIS_FAILED",
            correlation_id=effective_cid)
        if raise_on_error:
            raise
        return db.query(ResearchRun).filter(ResearchRun.id == run_id).first()

    finally:
        ownership_lost.set()
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


_ORIG_RETRIEVE = retrieve_multi_document_candidates
_ORIG_SYNTH = synthesize_research_answer
_ORIG_PERSIST = persist_document_provenance
