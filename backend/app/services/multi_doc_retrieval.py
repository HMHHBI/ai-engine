from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Chat,
    Document,
    DocumentChunk,
    WorkspaceDocument,
)
from app.services.embedding_service import EmbeddingService

MAX_SELECTED_DOCUMENTS = 20
MAX_CANDIDATES = 100
DEFAULT_CANDIDATES = 40
CANDIDATE_POOL_PER_CHANNEL = 60


class DocumentSelectionError(ValueError):
    """Raised when a requested document selection is not valid for a workspace."""


def _validate_document_selection(
    db: Session,
    *,
    workspace_id: int,
    document_ids: list[int],
) -> list[dict[str, Any]]:
    if workspace_id <= 0:
        raise DocumentSelectionError("Invalid workspace selection.")

    if not document_ids or len(document_ids) < 2:
        raise DocumentSelectionError("At least two documents must be selected.")

    if len(document_ids) > MAX_SELECTED_DOCUMENTS:
        raise DocumentSelectionError(
            f"No more than {MAX_SELECTED_DOCUMENTS} documents may be selected."
        )

    if any(document_id <= 0 for document_id in document_ids):
        raise DocumentSelectionError("Invalid document selection.")

    if len(set(document_ids)) != len(document_ids):
        raise DocumentSelectionError("Duplicate document IDs are not allowed.")

    rows = db.execute(
        select(
            Document.id,
            Document.filename,
            Document.status,
            Document.user_id,
            Document.chat_id,
        )
        .join(
            WorkspaceDocument,
            WorkspaceDocument.document_id == Document.id,
        )
        .join(
            Chat,
            Chat.id == Document.chat_id,
        )
        .where(
            WorkspaceDocument.workspace_id == workspace_id,
            Document.id.in_(document_ids),
            Document.status == "ready",
            Chat.user_id == Document.user_id,
        )
    ).all()

    documents_by_id = {
        int(row.id): {
            "document_id": int(row.id),
            "filename": str(row.filename),
            "status": str(row.status),
            "user_id": int(row.user_id),
            "chat_id": int(row.chat_id),
        }
        for row in rows
    }

    # Keep the failure response generic: do not disclose whether an
    # unreturned ID exists in another workspace or is still processing.
    if set(documents_by_id) != set(document_ids):
        raise DocumentSelectionError(
            "Every selected document must be ready and associated with this workspace."
        )

    return [documents_by_id[document_id] for document_id in document_ids]

validate_document_selection = _validate_document_selection


def _normalize_scores(
    values: dict[int, float],
) -> dict[int, float]:
    if not values:
        return {}

    minimum = min(values.values())
    maximum = max(values.values())

    if maximum - minimum <= 1e-12:
        return {key: 1.0 for key in values}

    return {
        key: (value - minimum) / (maximum - minimum) for key, value in values.items()
    }


async def retrieve_multi_document_candidates(
    db: Session,
    *,
    workspace_id: int,
    requester_id: int,
    document_ids: list[int],
    query: str,
    candidate_limit: int = DEFAULT_CANDIDATES,
) -> list[dict[str, Any]]:
    """
    Retrieve a globally ranked candidate pool across explicitly selected,
    ready documents associated with a workspace.

    Workspace membership and role authorization must be checked by the
    caller before this function is invoked.
    """
    del requester_id  # Membership is enforced by require_workspace_role.

    normalized_query = (query or "").strip()
    if not normalized_query:
        raise ValueError("Research query cannot be blank.")

    if candidate_limit <= 0 or candidate_limit > MAX_CANDIDATES:
        raise ValueError(f"candidate_limit must be between 1 and {MAX_CANDIDATES}.")

    selected_documents = _validate_document_selection(
        db,
        workspace_id=workspace_id,
        document_ids=document_ids,
    )
    selected_ids = [item["document_id"] for item in selected_documents]
    document_metadata = {item["document_id"]: item for item in selected_documents}

    embedding_provider = getattr(
        settings.DEFAULT_EMBEDDING_PROVIDER,
        "value",
        str(settings.DEFAULT_EMBEDDING_PROVIDER),
    )

    query_vector = None
    try:
        query_vector = await EmbeddingService.generate_embedding(
            normalized_query,
            embedding_provider,
        )
    except Exception:
        # Lexical retrieval remains available if the embedding backend
        # is unavailable. Do not silently substitute another tenant scope.
        query_vector = None

    merged: dict[int, dict[str, Any]] = {}
    dense_raw: dict[int, float] = {}
    lexical_raw: dict[int, float] = {}

    base_conditions = (
        DocumentChunk.document_id.in_(selected_ids),
        Document.status == "ready",
        WorkspaceDocument.workspace_id == workspace_id,
        WorkspaceDocument.document_id == Document.id,
        Chat.id == Document.chat_id,
        Chat.user_id == Document.user_id,
    )

    if query_vector:
        distance_expr = DocumentChunk.embedding.cosine_distance(query_vector).label(
            "distance"
        )

        dense_rows = db.execute(
            select(
                DocumentChunk,
                Document.filename,
                distance_expr,
            )
            .join(
                Document,
                Document.id == DocumentChunk.document_id,
            )
            .join(
                WorkspaceDocument,
                WorkspaceDocument.document_id == Document.id,
            )
            .join(
                Chat,
                Chat.id == Document.chat_id,
            )
            .where(
                *base_conditions,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance_expr.asc(), DocumentChunk.id.asc())
            .limit(CANDIDATE_POOL_PER_CHANNEL)
        ).all()

        for chunk, filename, distance in dense_rows:
            chunk_id = int(chunk.id)
            distance_value = float(distance)
            dense_raw[chunk_id] = 1.0 - distance_value
            merged[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": int(chunk.document_id),
                "filename": str(filename),
                "page_number": (
                    int(chunk.page_number) if chunk.page_number is not None else None
                ),
                "chunk_index": (
                    int(chunk.chunk_index) if chunk.chunk_index is not None else None
                ),
                "content": str(chunk.content),
                "distance": distance_value,
            }

    ts_vector = func.to_tsvector("english", DocumentChunk.content)
    ts_query = func.plainto_tsquery("english", normalized_query)
    lexical_expr = func.ts_rank_cd(
        ts_vector,
        ts_query,
        32,
    ).label("lexical_score")

    lexical_rows = db.execute(
        select(
            DocumentChunk,
            Document.filename,
            lexical_expr,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .join(
            WorkspaceDocument,
            WorkspaceDocument.document_id == Document.id,
        )
        .join(
            Chat,
            Chat.id == Document.chat_id,
        )
        .where(
            *base_conditions,
            ts_vector.op("@@")(ts_query),
        )
        .order_by(lexical_expr.desc(), DocumentChunk.id.asc())
        .limit(CANDIDATE_POOL_PER_CHANNEL)
    ).all()

    for chunk, filename, score in lexical_rows:
        chunk_id = int(chunk.id)
        lexical_raw[chunk_id] = float(score)

        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": int(chunk.document_id),
                "filename": str(filename),
                "page_number": (
                    int(chunk.page_number) if chunk.page_number is not None else None
                ),
                "chunk_index": (
                    int(chunk.chunk_index) if chunk.chunk_index is not None else None
                ),
                "content": str(chunk.content),
                "distance": None,
            }

    if not merged:
        return []

    normalized_dense = _normalize_scores(dense_raw)
    normalized_lexical = _normalize_scores(lexical_raw)

    dense_available = bool(normalized_dense)
    lexical_available = bool(normalized_lexical)

    for chunk_id, candidate in merged.items():
        dense_score = normalized_dense.get(chunk_id, 0.0)
        lexical_score = normalized_lexical.get(chunk_id, 0.0)

        if dense_available and lexical_available:
            score = 0.55 * dense_score + 0.45 * lexical_score
        elif dense_available:
            score = dense_score
        else:
            score = lexical_score

        candidate["dense_score"] = round(dense_score, 6)
        candidate["lexical_score"] = round(lexical_score, 6)
        candidate["score"] = round(score, 6)
        candidate["workspace_id"] = workspace_id
        candidate["document_metadata"] = document_metadata[candidate["document_id"]]

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            -item["score"],
            item["document_id"],
            item["chunk_id"],
        ),
    )

    return ranked[:candidate_limit]
