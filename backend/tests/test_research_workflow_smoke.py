"""
Isolated Research Workflow Smoke Profile (Phase 2B / PR 2).

Validates the end-to-end multi-document research synthesis workflow:
1. Deterministic seeding of multi-paper research workspaces.
2. Isolated synthesis run creation and lifecycle verification.
3. Structured facet output contract (methodology, datasets, metrics, findings, limitations).
4. Citation attribution and passage provenance verification.
5. Workspace boundary isolation and unselected document rejection.
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
    """Deterministic LLM Provider specifically for the isolated smoke profile."""

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
) -> Document:
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
    return doc


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

    doc_a = create_smoke_document(
        db_session,
        user=user,
        filename="paper_a.pdf",
        content="Linear attention mechanisms improve latency during benchmark evaluations significantly.",
    )
    doc_b = create_smoke_document(
        db_session,
        user=user,
        filename="paper_b.pdf",
        content="Attention mechanisms show latency reductions and empirical accuracy on GLUE benchmarks.",
    )

    associate_smoke_doc(db_session, ws_id, doc_a.id, user.id)
    associate_smoke_doc(db_session, ws_id, doc_b.id, user.id)

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

    # 4. Assert Citations & Provenance
    citations = run_payload.get("citations")
    assert isinstance(citations, list)
    assert len(citations) >= 2
    cited_doc_ids = {c["document_id"] for c in citations}
    assert cited_doc_ids == {doc_a.id, doc_b.id}
    for c in citations:
        assert c["chunk_id"] > 0
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
    Smoke profile error boundary: guards against documents not in workspace
    or documents not yet in 'ready' status.
    """
    user = create_smoke_user(db_session, "smoke-guards@example.test")
    ws_id = create_smoke_workspace(client, user, "Smoke Guards Workspace")

    doc_processing = create_smoke_document(
        db_session,
        user=user,
        filename="processing.pdf",
        content="Processing content...",
        status="processing",
    )
    associate_smoke_doc(db_session, ws_id, doc_processing.id, user.id)

    # 1. Unready document rejection
    res = client.post(
        f"/workspaces/{ws_id}/research/runs",
        headers=smoke_auth_headers(user),
        json={
            "query": "test unready guard",
            "document_ids": [doc_processing.id],
        },
    )
    assert res.status_code in (400, 422)

    # 2. Document outside workspace rejection
    other_user = create_smoke_user(db_session, "other-user@example.test")
    doc_outside = create_smoke_document(
        db_session,
        user=other_user,
        filename="outside.pdf",
        content="Sensitive foreign content.",
        status="ready",
    )
    res_outside = client.post(
        f"/workspaces/{ws_id}/research/runs",
        headers=smoke_auth_headers(user),
        json={
            "query": "test outside guard",
            "document_ids": [doc_outside.id],
        },
    )
    assert res_outside.status_code in (400, 404, 422)
