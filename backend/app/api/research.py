from __future__ import annotations

import logging

import asyncio
import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.logging import correlation_id_var
from app.core.rate_limiter import limiter
from app.db.models import (
    ResearchRun,
    ResearchRunDocument,
    User,
)
from app.db.session import SessionLocal, get_db
from app.schemas.research_schema import (
    ACTIVE_RESEARCH_STATUSES,
    TERMINAL_RESEARCH_STATUSES,
    ResearchCitationOut,
    ResearchFacetsOut,
    ResearchRunCancelOut,
    ResearchRunCreate,
    ResearchRunListOut,
    ResearchRunOut,
)
from app.services.multi_doc_retrieval import (
    DocumentSelectionError,
    validate_document_selection,
)
from app.services.research_execution import (
    persist_document_provenance as _persist_document_provenance,
    retrieve_multi_document_candidates,
    synthesize_research_answer,
    ResearchRunTerminalError,
    execute_research_run,
    get_lifecycle_snapshot,
    request_research_run_cancellation,
)
from app.services.research_export import (
    build_research_export_bundle,
    content_disposition_attachment,
    render_research_export,
    research_export_filename,
)
from app.services.research_synthesis import SynthesisValidationError
from app.services.workspace_auth import require_workspace_role
from app.workers.research_worker import (
    ResearchRunDispatcher,
    create_research_run_outbox,
    run_research_job_in_background,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["research"])


def _run_response(run: ResearchRun) -> ResearchRunOut:
    stored_answer = run.answer or {}
    answer_text = stored_answer.get("answer")
    citations_data = stored_answer.get("citations") or []
    facets_data = stored_answer.get("facets")

    citations = [
        ResearchCitationOut.model_validate(citation) for citation in citations_data
    ]

    facets = None
    if isinstance(facets_data, dict):
        try:
            facets = ResearchFacetsOut.model_validate(facets_data)
        except Exception:
            facets = None

    return ResearchRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        requester_id=run.requester_id,
        query=run.query,
        status=run.status,
        answer=answer_text,
        facets=facets,
        citations=citations,
        run_metadata=run.run_metadata or {},
        created_at=run.created_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
    )


def _format_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post(
    "/workspaces/{workspace_id}/research/runs",
    response_model=ResearchRunOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def create_research_run(
    request: Request,
    response: Response,
    workspace_id: int,
    payload: ResearchRunCreate,
    background_tasks: BackgroundTasks,
    async_mode: bool = Query(default=False),
    prefer: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    access=Depends(require_workspace_role("researcher")),
    db: Session = Depends(get_db),
):
    try:
        validate_document_selection(
            db,
            workspace_id=workspace_id,
            document_ids=payload.document_ids,
        )
    except DocumentSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    cid = correlation_id_var.get()
    is_async = async_mode or (
        prefer is not None and "respond-async" in prefer.lower()
    )

    run = ResearchRun(
        workspace_id=workspace_id,
        requester_id=current_user.id,
        query=payload.query,
        status="queued",
        run_metadata={
            "selected_document_ids": payload.document_ids,
            "retrieval": {
                "strategy": "global_dense_lexical_normalized",
                "candidate_limit": 40,
            },
            "lifecycle": {
                "correlation_id": cid,
                "cancel_requested": False,
                "attempt_count": 0,
            },
        },
    )
    db.add(run)
    if is_async:
        db.flush()
        outbox = create_research_run_outbox(
            db,
            run=run,
            correlation_id=cid,
        )
        db.commit()
        db.refresh(run)
        db.refresh(outbox)
        response.status_code = status.HTTP_202_ACCEPTED
        try:
            await ResearchRunDispatcher.publish_outbox_event(
                db,
                outbox_id=outbox.id,
            )
        except Exception:
            # Outbox record remains safely persisted as `pending` for worker sweep
            logger.warning(
                "research_run_immediate_publish_deferred",
                extra={
                    "event": "research_run_immediate_publish_deferred",
                    "run_id": run.id,
                    "outbox_id": outbox.id,
                },
            )
        return _run_response(run)

    db.commit()
    db.refresh(run)

    # Default synchronous execution mode (backward-compatible contract)
    try:
        completed_run = await execute_research_run(
            db,
            run_id=run.id,
            correlation_id=cid,
            raise_on_error=True,
        )
        assert completed_run is not None
        return _run_response(completed_run)
    except DocumentSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except (SynthesisValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The research synthesis response could not be validated.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Research synthesis failed.",
        ) from exc


@router.get(
    "/workspaces/{workspace_id}/research/runs",
    response_model=ResearchRunListOut,
)
def list_research_runs(
    workspace_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    access=Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
):
    query = (
        db.query(ResearchRun)
        .filter(ResearchRun.workspace_id == workspace_id)
        .order_by(ResearchRun.created_at.desc())
    )
    total = query.count()
    runs = query.offset(offset).limit(limit).all()

    return ResearchRunListOut(
        items=[_run_response(r) for r in runs],
        total=total,
    )


@router.get(
    "/workspaces/{workspace_id}/research/runs/{run_id}",
    response_model=ResearchRunOut,
)
def get_research_run(
    workspace_id: int,
    run_id: int,
    access=Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
):
    run = (
        db.query(ResearchRun)
        .options(joinedload(ResearchRun.workspace))
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id,
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    return _run_response(run)


@router.get(
    "/workspaces/{workspace_id}/research/runs/{run_id}/events",
)
async def stream_research_run_events(
    request: Request,
    workspace_id: int,
    run_id: int,
    poll_interval: float = Query(default=0.35, ge=0.05, le=5.0),
    access=Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    initial_run = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id,
        )
        .first()
    )
    if initial_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    async def event_generator():
        last_signature: tuple[str, bool, str | None] | None = None
        while True:
            if await request.is_disconnected():
                break

            with SessionLocal() as poll_db:
                current = (
                    poll_db.query(ResearchRun)
                    .filter(
                        ResearchRun.id == run_id,
                        ResearchRun.workspace_id == workspace_id,
                    )
                    .first()
                )
                if current is None:
                    yield _format_sse(
                        "error",
                        {"run_id": run_id, "detail": "Research run not found."},
                    )
                    break

                snapshot = get_lifecycle_snapshot(current)
                signature = (
                    snapshot["status"],
                    snapshot["cancel_requested"],
                    snapshot["updated_at"],
                )
                if signature != last_signature:
                    last_signature = signature
                    yield _format_sse("stage", snapshot)

                if snapshot["status"] in TERMINAL_RESEARCH_STATUSES:
                    yield _format_sse("done", snapshot)
                    break

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/workspaces/{workspace_id}/research/runs/{run_id}/cancel",
    response_model=ResearchRunCancelOut,
)
def cancel_research_run(
    workspace_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    access=Depends(require_workspace_role("researcher")),
    db: Session = Depends(get_db),
) -> ResearchRunCancelOut:
    existing = (
        db.query(ResearchRun)
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id,
        )
        .first()
    )
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    if existing.requester_id != current_user.id and access.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the run requester or a workspace admin can cancel this research run.",
        )

    try:
        updated_run, cancel_requested = request_research_run_cancellation(
            db,
            workspace_id=workspace_id,
            run_id=run_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ResearchRunTerminalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    message = (
        "Research run cancelled."
        if updated_run.status == "cancelled"
        else "Cancellation requested; run will stop at the next safe checkpoint."
    )

    return ResearchRunCancelOut(
        id=updated_run.id,
        workspace_id=updated_run.workspace_id,
        status=updated_run.status,
        cancel_requested=cancel_requested,
        message=message,
    )


@router.get(
    "/workspaces/{workspace_id}/research/runs/{run_id}/export",
    response_class=Response,
    responses={
        200: {
            "description": "A reproducible Markdown or JSON research artifact.",
            "content": {
                "text/markdown": {},
                "application/json": {},
            },
        },
        404: {"description": "Workspace or research run not found."},
        409: {"description": "Research run has not completed."},
        422: {"description": "Research run failed or export data is invalid."},
    },
)
def export_research_run(
    workspace_id: int,
    run_id: int,
    export_format: Literal["markdown", "json"] = Query(
        default="markdown",
        alias="format",
    ),
    access=Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> Response:
    run = (
        db.query(ResearchRun)
        .options(
            joinedload(ResearchRun.workspace),
            joinedload(ResearchRun.document_associations).joinedload(
                ResearchRunDocument.document
            ),
        )
        .filter(
            ResearchRun.id == run_id,
            ResearchRun.workspace_id == workspace_id,
        )
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run not found.",
        )

    if run.status != "completed":
        if run.status in ACTIVE_RESEARCH_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Research run cannot be exported while its status is "
                    f"'{run.status}'. Wait until the run is completed."
                ),
            )

        if run.status == "failed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed research runs cannot be exported.",
            )

        if run.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cancelled research runs cannot be exported.",
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed research runs can be exported.",
        )

    try:
        bundle = build_research_export_bundle(run)
        body, media_type = render_research_export(
            bundle,
            export_format=export_format,
        )
        filename = research_export_filename(
            workspace_name=run.workspace.name,
            workspace_id=run.workspace_id,
            run_id=run.id,
            export_format=export_format,
        )
        disposition = content_disposition_attachment(filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The research run does not contain valid export data.",
        ) from exc

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
        status_code=status.HTTP_200_OK,
    )
