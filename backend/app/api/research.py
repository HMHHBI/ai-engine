from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.db.models import (
    Document,
    ResearchRun,
    ResearchRunDocument,
    User,
    WorkspaceDocument,
)
from app.db.session import get_db
from app.schemas.research_schema import (
    ResearchCitationOut,
    ResearchFacetsOut,
    ResearchRunCreate,
    ResearchRunListOut,
    ResearchRunOut,
)
from app.services.audit_log import record_audit_event
from app.services.multi_doc_retrieval import (
    validate_document_selection,
    DocumentSelectionError,
    retrieve_multi_document_candidates,
)
from app.services.research_export import (
    build_research_export_bundle,
    content_disposition_attachment,
    render_research_export,
    research_export_filename,
)
from app.services.research_synthesis import (
    SynthesisValidationError,
    synthesize_research_answer,
)
from app.services.workspace_auth import require_workspace_role

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


def _persist_document_provenance(
    db: Session,
    *,
    run: ResearchRun,
    document_ids: list[int],
    candidates: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> None:
    citations_by_document: dict[int, list[dict[str, Any]]] = {
        document_id: [] for document_id in document_ids
    }

    for citation in citations:
        citations_by_document.setdefault(
            int(citation["document_id"]),
            [],
        ).append(citation)

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
        .join(
            WorkspaceDocument,
            WorkspaceDocument.document_id == Document.id,
        )
        .filter(
            WorkspaceDocument.workspace_id == run.workspace_id,
            Document.id.in_(document_ids),
        )
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
                },
            )
        )


@router.post(
    "/workspaces/{workspace_id}/research/runs",
    response_model=ResearchRunOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def create_research_run(
    request: Request,
    workspace_id: int,
    payload: ResearchRunCreate,
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

    run = ResearchRun(
        workspace_id=workspace_id,
        requester_id=current_user.id,
        query=payload.query,
        status="running",
        run_metadata={
            "selected_document_ids": payload.document_ids,
            "retrieval": {
                "strategy": "global_dense_lexical_normalized",
                "candidate_limit": 40,
            },
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        candidates = await retrieve_multi_document_candidates(
            db,
            workspace_id=workspace_id,
            requester_id=current_user.id,
            document_ids=payload.document_ids,
            query=payload.query,
            candidate_limit=40,
        )

        result = await synthesize_research_answer(
            query=payload.query,
            candidates=candidates,
        )

        citation_payloads = result["citations"]

        _persist_document_provenance(
            db,
            run=run,
            document_ids=payload.document_ids,
            candidates=result["evidence"],
            citations=citation_payloads,
        )

        run.answer = {
            "answer": result["answer"],
            "citations": citation_payloads,
            "facets": result.get("facets"),
        }
        run.run_metadata = {
            **(run.run_metadata or {}),
            "provider": result["provider"],
            "model": result["model"],
            "candidate_count": len(result["evidence"]),
            "citation_count": len(citation_payloads),
            "completed_document_ids": sorted(
                {int(candidate["document_id"]) for candidate in result["evidence"]}
            ),
        }
        run.status = "completed"
        run.error_message = None
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)

        return _run_response(run)

    except DocumentSelectionError as exc:
        db.rollback()
        failed_run = (
            db.query(ResearchRun)
            .filter(
                ResearchRun.id == run.id,
                ResearchRun.workspace_id == workspace_id,
            )
            .first()
        )

        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_message = str(exc)
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    except (SynthesisValidationError, ValueError) as exc:
        db.rollback()
        failed_run = (
            db.query(ResearchRun)
            .filter(
                ResearchRun.id == run.id,
                ResearchRun.workspace_id == workspace_id,
            )
            .first()
        )

        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_message = str(exc)[:1000]
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The research synthesis response could not be validated.",
        ) from exc

    except Exception as exc:
        db.rollback()
        failed_run = (
            db.query(ResearchRun)
            .filter(
                ResearchRun.id == run.id,
                ResearchRun.workspace_id == workspace_id,
            )
            .first()
        )

        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_message = "Research synthesis failed."
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()

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
        if run.status in {"queued", "running"}:
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
