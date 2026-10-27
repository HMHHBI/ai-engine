"""
Isolated Research Workflow Smoke Profile (Phase 2B / PR 2).

Validates the end-to-end multi-document research synthesis workflow:
1. Deterministic seeding of multi-paper research workspaces.
2. Isolated synthesis run creation and lifecycle verification.
3. Structured facet output contract (methodology, datasets, metrics, findings, limitations).
4. Citation attribution and passage/chunk provenance verification.
5. Workspace boundary isolation and unready document rejection.

Note on Architecture & Retrieval:
The underlying backend retrieval pipeline performs keyword and token matching to rank
and inject document chunks into prompt citations ([C1], [C2]). The SmokeResearchProvider
acts as a deterministic LLM mock that emits structured facets referencing those citations.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.models import (
    Chat,
    Document,
    DocumentChunk,
    ResearchRun,
    ResearchRunDocument,
    User,
    WorkspaceDocument,
)
from app.services.embedding_service import EmbeddingService
from app.services.providers.factory import LLMProviderFactory


class SmokeResearchProvider:
    """Deterministic LLM Provider returning static mock response for the smoke test."""

    async def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.1,
        **kwargs,
    ) -> str:
        return json.dumps({
            "facets": {
                "methodology": "Comparative evaluation of transformer self-attention variants [C1] [C2].",
                "datasets": "Trained on Common Crawl and tested on GLUE benchmarks [C1].",
                "metrics": "Evaluated using MRR@10 and F1 accuracy score [C2].",
                "findings": "Significant latency reductions observed without accuracy degradation [C1] [C2].",
                "limitations": "Constrained by context window scaling limits [C2].",
            },
            "citations": ["C1", "C2"],
        })

    async def generate_stream(self, *args, **kwargs):
        if False:
            yield ""


@pytest.fixture()
def smoke_research_providers(monkeypatch):
    monkeypatch.setattr(
        EmbeddingService,
        "generate_embedding",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        LLMProviderFactory,
        "get_provider",
        lambda *args, **kwargs: SmokeResearchProvider(),
    )


def create_smoke_user(db_session: Session, email: str) -> User:
    user = User(
        name="Smoke Test Researcher",
        email=email,
        password="test-password-hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def smoke_auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


def create_smoke_workspace(client: TestClient, user: User, name: str) -> int:
    response = client.post(
        "/workspaces/",
        headers=smoke_auth_headers(user),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def create_smoke_document(
    db_session: Session,
    *,
    user: User,
    filename: str,
    content: str,
    status: str = "ready",
) -> tuple[Document, DocumentChunk]:
    chat = Chat(user_id=user.id, title=f"Chat for {filename}")
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    doc = Document(
        user_id=user.id,
        chat_id=chat.id,
        filename=filename,
        mime_type="application/pdf",
        status=status,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    chunk = DocumentChunk(
        chat_id=chat.id,
        document_id=doc.id,
        content=content,
        page_number=1,
        chunk_index=0,
        embedding=None,
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)
    return doc, chunk


def associate_smoke_doc(
    db_session: Session,
    workspace_id: int,
    document_id: int,
    added_by: int,
) -> None:
    db_session.add(
        WorkspaceDocument(
            workspace_id=workspace_id,
            document_id=document_id,
            added_by=added_by,
        )
    )
    db_session.commit()


@pytest.mark.smoke_research
def test_isolated_research_workflow_smoke_profile(
    client: TestClient,
    db_session: Session,
    smoke_research_providers,
):
    """
    End-to-end smoke test validating multi-document synthesis execution,
    facet conformance, citation mapping, and database persistence.
    """
    user = create_smoke_user(db_session, "smoke-runner@example.test")
    ws_id = create_smoke_workspace(client, user, "Smoke Research Workspace")

    doc_a, chunk_a = create_smoke_document(
        db_session,
        user=user,
        filename="paper_a.pdf",
        content="Linear attention mechanisms improve latency during benchmark evaluations significantly.",
    )
    doc_b, chunk_b = create_smoke_document(
        db_session,
        user=user,
        filename="paper_b.pdf",
        content="Attention mechanisms show latency reductions and empirical accuracy on GLUE benchmarks.",
    )

    associate_smoke_doc(db_session, ws_id, doc_a.id, user.id)
    associate_smoke_doc(db_session, ws_id, doc_b.id, user.id)

    # Provenance tracking: map chunk_id to expected document_id
    seeded_chunk_to_doc = {
        chunk_a.id: doc_a.id,
        chunk_b.id: doc_b.id,
    }

    # 1. Trigger synthesis run
    response = client.post(
        f"/workspaces/{ws_id}/research/runs",
        headers=smoke_auth_headers(user),
        json={
            "query": "attention mechanisms latency",
            "document_ids": [doc_a.id, doc_b.id],
        },
    )
    assert response.status_code == 201, response.text
    run_payload = response.json()

    # 2. Assert Run Contract
    assert run_payload["status"] == "completed"
    assert "id" in run_payload
    run_id = run_payload["id"]

    # 3. Assert Structured Facets
    facets = run_payload.get("facets")
    assert isinstance(facets, dict)
    for expected_facet in ("methodology", "datasets", "metrics", "findings", "limitations"):
        assert expected_facet in facets
        assert isinstance(facets[expected_facet], str)
        assert len(facets[expected_facet].strip()) > 0

    # 4. Assert Citations & Precise Chunk Provenance
    citations = run_payload.get("citations")
    assert isinstance(citations, list)
    assert len(citations) >= 2
    cited_doc_ids = {c["document_id"] for c in citations}
    assert cited_doc_ids == {doc_a.id, doc_b.id}

    for c in citations:
        c_chunk_id = c["chunk_id"]
        c_doc_id = c["document_id"]
        assert c_chunk_id in seeded_chunk_to_doc, f"Unknown chunk_id {c_chunk_id} cited"
        assert seeded_chunk_to_doc[c_chunk_id] == c_doc_id, (
            f"Chunk ownership mismatch: chunk {c_chunk_id} belongs to "
            f"doc {seeded_chunk_to_doc[c_chunk_id]}, but cited under doc {c_doc_id}"
        )
        assert c["filename"] in ("paper_a.pdf", "paper_b.pdf")
        assert len(c["excerpt"]) > 0

    # 5. Verify Relational Persistence
    run_docs = (
        db_session.query(ResearchRunDocument)
        .filter(ResearchRunDocument.research_run_id == run_id)
        .all()
    )
    assert {rd.document_id for rd in run_docs} == {doc_a.id, doc_b.id}

    # 6. Verify Fetch By Run ID
    get_res = client.get(
        f"/workspaces/{ws_id}/research/runs/{run_id}",
        headers=smoke_auth_headers(user),
    )
    assert get_res.status_code == 200
    fetched_run = get_res.json()
    assert fetched_run["id"] == run_id
    assert fetched_run["status"] == "completed"
    assert fetched_run["facets"] == facets


@pytest.mark.smoke_research
def test_smoke_profile_guards_unselected_and_unready_documents(
    client: TestClient,
    db_session: Session,
    smoke_research_providers,
):
    """
    Smoke profile error boundary:
    1. Rejects unready documents (e.g. status='processing').
    2. Rejects documents owned by the same user but assigned to a different workspace (isolated workspace boundary).
    """
    user = create_smoke_user(db_session, "smoke-guards@example.test")
    ws_target = create_smoke_workspace(client, user, "Target Research Workspace")
    ws_other = create_smoke_workspace(client, user, "Other Distinct Workspace")

    doc_processing, _ = create_smoke_document(
        db_session,
        user=user,
        filename="processing.pdf",
        content="Processing content...",
        status="processing",
    )
    associate_smoke_doc(db_session, ws_target, doc_processing.id, user.id)

    # 1. Unready document rejection
    res = client.post(
        f"/workspaces/{ws_target}/research/runs",
        headers=smoke_auth_headers(user),
        json={
            "query": "test unready guard",
            "document_ids": [doc_processing.id],
        },
    )
    assert res.status_code in (400, 422)

    # 2. Workspace boundary isolation: document is owned by the SAME user,
    # but strictly associated with ws_other, not ws_target.
    doc_in_other_ws, _ = create_smoke_document(
        db_session,
        user=user,
        filename="other_workspace_doc.pdf",
        content="Content belonging to another workspace.",
        status="ready",
    )
    associate_smoke_doc(db_session, ws_other, doc_in_other_ws.id, user.id)

    res_cross_workspace = client.post(
        f"/workspaces/{ws_target}/research/runs",
        headers=smoke_auth_headers(user),
        json={
            "query": "test cross workspace guard",
            "document_ids": [doc_in_other_ws.id],
        },
    )
    # Must reject because document is not in ws_target
    assert res_cross_workspace.status_code in (400, 404, 422)
