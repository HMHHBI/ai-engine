from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
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
    ResearchRunCreate,
    ResearchRunOut,
)
from app.services.multi_doc_retrieval import (
    DocumentSelectionError,
    retrieve_multi_document_candidates,
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

    citations = [
        ResearchCitationOut.model_validate(citation) for citation in citations_data
    ]

    return ResearchRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        requester_id=run.requester_id,
        query=run.query,
        status=run.status,
        answer=answer_text,
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
async def create_research_run(
    workspace_id: int,
    payload: ResearchRunCreate,
    current_user: User = Depends(get_current_user),
    access=Depends(require_workspace_role("researcher")),
    db: Session = Depends(get_db),
):
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
