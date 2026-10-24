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


class FakeResearchProvider:
    async def generate_response(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.1,
        **kwargs,
    ) -> str:
        # If 3 citations are in the prompt
        if "[C3]" in prompt:
            return json.dumps({
                "facets": {
                    "methodology": "Methodology comparison across papers [C1].",
                    "datasets": "Dataset benchmarks evaluated [C2].",
                    "metrics": "Metrics and evaluation criteria [C3].",
                    "findings": "Combined findings and consensus [C1] [C2].",
                    "limitations": "Identified limitations across studies [C3].",
                },
                "citations": ["C1", "C2", "C3"],
            })
        return json.dumps({
            "facets": {
                "methodology": "Solar revenue growth methodology [C1].",
                "datasets": "Production datasets [C2].",
                "metrics": "Revenue percentages [C1].",
                "findings": "Consistent positive trends [C1] [C2].",
                "limitations": "Limited duration [C2].",
            },
            "citations": ["C1", "C2"],
        })

    async def generate_stream(self, *args, **kwargs):
        if False:
            yield ""


def create_user(
    db_session: Session,
    *,
    email: str,
) -> User:
    user = User(
        name="Research Test User",
        email=email,
        password="test-password-hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


def create_workspace(
    client: TestClient,
    user: User,
    *,
    name: str,
) -> int:
    response = client.post(
        "/workspaces/",
        headers=auth_headers(user),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def create_ready_document(
    db_session: Session,
    *,
    user: User,
    filename: str,
    content: str | None = None,
    status: str = "ready",
) -> Document:
    chat = Chat(
        user_id=user.id,
        title=f"Chat for {filename}",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    document = Document(
        user_id=user.id,
        chat_id=chat.id,
        filename=filename,
        mime_type="application/pdf",
        status=status,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    if content is not None:
        chunk = DocumentChunk(
            chat_id=chat.id,
            document_id=document.id,
            content=content,
            page_number=1,
            chunk_index=0,
            embedding=None,
        )
        db_session.add(chunk)
        db_session.commit()

    return document


def associate_document(
    db_session: Session,
    *,
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


@pytest.fixture()
def fake_research_providers(monkeypatch):
    monkeypatch.setattr(
        EmbeddingService,
        "generate_embedding",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        LLMProviderFactory,
        "get_provider",
        lambda *args, **kwargs: FakeResearchProvider(),
    )


def test_synthesis_retrieves_evidence_from_two_documents(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
):
    user = create_user(
        db_session,
        email="research-two-docs@example.test",
    )
    workspace_id = create_workspace(
        client,
        user,
        name="Multi-document workspace",
    )

    document_a = create_ready_document(
        db_session,
        user=user,
        filename="solar-report-a.pdf",
        content=(
            "Solar revenue increased during the first reporting period. "
            "The report attributes growth to higher production."
        ),
    )
    document_b = create_ready_document(
        db_session,
        user=user,
        filename="solar-report-b.pdf",
        content=(
            "Solar revenue increased during the second reporting period. "
            "The report attributes growth to improved capacity."
        ),
    )

    associate_document(
        db_session,
        workspace_id=workspace_id,
        document_id=document_a.id,
        added_by=user.id,
    )
    associate_document(
        db_session,
        workspace_id=workspace_id,
        document_id=document_b.id,
        added_by=user.id,
    )

    response = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(user),
        json={
            "query": "solar revenue growth",
            "document_ids": [document_a.id, document_b.id],
        },
    )

    assert response.status_code == 201, response.text
    result = response.json()

    assert result["status"] == "completed"
    assert result["facets"] is not None
    assert "methodology" in result["facets"]
    assert "limitations" in result["facets"]
    assert "[C1]" in result["answer"]
    assert "[C2]" in result["answer"]

    cited_document_ids = {citation["document_id"] for citation in result["citations"]}
    assert cited_document_ids == {document_a.id, document_b.id}

    assert all(
        citation["chunk_id"] > 0 and citation["filename"] and citation["excerpt"]
        for citation in result["citations"]
    )

    associations = (
        db_session.query(ResearchRunDocument)
        .filter(ResearchRunDocument.research_run_id == result["id"])
        .all()
    )
    assert {item.document_id for item in associations} == {
        document_a.id,
        document_b.id,
    }


def test_three_paper_synthesis_and_evidence_isolation(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
):
    user = create_user(
        db_session,
        email="research-three-papers@example.test",
    )
    workspace_id = create_workspace(
        client,
        user,
        name="Three-paper synthesis workspace",
    )

    doc1 = create_ready_document(
        db_session,
        user=user,
        filename="paper1.pdf",
        content="Optimization benchmarks for transformer attention mechanisms.",
    )
    doc2 = create_ready_document(
        db_session,
        user=user,
        filename="paper2.pdf",
        content="Optimization benchmarks across vision reasoning datasets.",
    )
    doc3 = create_ready_document(
        db_session,
        user=user,
        filename="paper3.pdf",
        content="Optimization benchmarks under edge device latency constraints.",
    )
    unselected_doc = create_ready_document(
        db_session,
        user=user,
        filename="unselected.pdf",
        content="Optimization benchmarks in an unselected document.",
    )

    for d in [doc1, doc2, doc3, unselected_doc]:
        associate_document(
            db_session,
            workspace_id=workspace_id,
            document_id=d.id,
            added_by=user.id,
        )

    response = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(user),
        json={
            "query": "optimization benchmarks",
            "document_ids": [doc1.id, doc2.id, doc3.id],
        },
    )

    assert response.status_code == 201, response.text
    result = response.json()
    run_id = result["id"]

    # Verify all 5 facets exist
    facets = result["facets"]
    assert facets is not None
    for facet_key in ["methodology", "datasets", "metrics", "findings", "limitations"]:
        assert facet_key in facets
        assert len(facets[facet_key]) > 0

    # Verify 3 papers are cited
    cited_doc_ids = {c["document_id"] for c in result["citations"]}
    assert cited_doc_ids == {doc1.id, doc2.id, doc3.id}

    # Verify unselected document is isolated (never present)
    assert unselected_doc.id not in cited_doc_ids
    for c in result["citations"]:
        assert c["document_id"] != unselected_doc.id
        assert c["filename"] != "unselected.pdf"

    # Test GET list runs endpoint for workspace
    list_response = client.get(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(user),
    )
    assert list_response.status_code == 200, list_response.text
    list_data = list_response.json()
    assert list_data["total"] >= 1
    run_item = next(r for r in list_data["items"] if r["id"] == run_id)
    assert run_item["facets"] is not None
    assert run_item["query"] == "optimization benchmarks"
    assert run_item["run_metadata"]["selected_document_ids"] == [doc1.id, doc2.id, doc3.id]

    # Verify export includes facets
    export_resp = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run_id}/export?format=json",
        headers=auth_headers(user),
    )
    assert export_resp.status_code == 200
    export_json = export_resp.json()
    assert "facets" in export_json
    assert export_json["facets"]["methodology"] == facets["methodology"]


def test_document_id_from_another_workspace_is_rejected(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
):
    user = create_user(
        db_session,
        email="research-cross-workspace@example.test",
    )
    workspace_a = create_workspace(
        client,
        user,
        name="Workspace A",
    )
    workspace_b = create_workspace(
        client,
        user,
        name="Workspace B",
    )

    document_a = create_ready_document(
        db_session,
        user=user,
        filename="workspace-a.pdf",
        content="Solar revenue increased in workspace A.",
    )
    document_b = create_ready_document(
        db_session,
        user=user,
        filename="workspace-b.pdf",
        content="Solar revenue increased in workspace B.",
    )

    associate_document(
        db_session,
        workspace_id=workspace_a,
        document_id=document_a.id,
        added_by=user.id,
    )
    associate_document(
        db_session,
        workspace_id=workspace_b,
        document_id=document_b.id,
        added_by=user.id,
    )

    response = client.post(
        f"/workspaces/{workspace_a}/research/runs",
        headers=auth_headers(user),
        json={
            "query": "solar revenue",
            "document_ids": [document_a.id, document_b.id],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Every selected document must be ready and associated with this workspace."
    )


@pytest.mark.parametrize(
    "document_status",
    ["processing", "failed"],
)
def test_unready_document_is_rejected_deterministically(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
    document_status: str,
):
    user = create_user(
        db_session,
        email=f"research-unready-{document_status}@example.test",
    )
    workspace_id = create_workspace(
        client,
        user,
        name="Unready document workspace",
    )

    ready_document = create_ready_document(
        db_session,
        user=user,
        filename="ready.pdf",
        content="Solar revenue information.",
    )
    unready_document = create_ready_document(
        db_session,
        user=user,
        filename=f"{document_status}.pdf",
        content=None,
        status=document_status,
    )

    associate_document(
        db_session,
        workspace_id=workspace_id,
        document_id=ready_document.id,
        added_by=user.id,
    )
    associate_document(
        db_session,
        workspace_id=workspace_id,
        document_id=unready_document.id,
        added_by=user.id,
    )

    response = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(user),
        json={
            "query": "solar revenue",
            "document_ids": [ready_document.id, unready_document.id],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Every selected document must be ready and associated with this workspace."
    )


def test_nonexistent_document_id_is_rejected(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
):
    user = create_user(
        db_session,
        email="research-invalid-id@example.test",
    )
    workspace_id = create_workspace(
        client,
        user,
        name="Invalid document workspace",
    )

    document = create_ready_document(
        db_session,
        user=user,
        filename="valid.pdf",
        content="Solar revenue information.",
    )
    associate_document(
        db_session,
        workspace_id=workspace_id,
        document_id=document.id,
        added_by=user.id,
    )

    response = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(user),
        json={
            "query": "solar revenue",
            "document_ids": [document.id, 999999999],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Every selected document must be ready and associated with this workspace."
    )


def test_viewer_can_read_run_but_cannot_start_research(
    client: TestClient,
    db_session: Session,
    fake_research_providers,
):
    owner = create_user(
        db_session,
        email="research-viewer-owner@example.test",
    )
    viewer = create_user(
        db_session,
        email="research-viewer@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="Viewer access workspace",
    )

    invite_response = client.post(
        f"/workspaces/{workspace_id}/members",
        headers=auth_headers(owner),
        json={"email": viewer.email, "role": "viewer"},
    )
    assert invite_response.status_code == 201, invite_response.text

    from app.db.models import WorkspaceMembership

    membership = (
        db_session.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == viewer.id,
        )
        .one()
    )
    membership.status = "active"
    db_session.commit()

    document_a = create_ready_document(
        db_session,
        user=owner,
        filename="viewer-a.pdf",
        content="Solar revenue increased in report A.",
    )
    document_b = create_ready_document(
        db_session,
        user=owner,
        filename="viewer-b.pdf",
        content="Solar revenue increased in report B.",
    )

    for document in (document_a, document_b):
        associate_document(
            db_session,
            workspace_id=workspace_id,
            document_id=document.id,
            added_by=owner.id,
        )

    create_response = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(owner),
        json={
            "query": "solar revenue",
            "document_ids": [document_a.id, document_b.id],
        },
    )
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    viewer_read = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run_id}",
        headers=auth_headers(viewer),
    )
    assert viewer_read.status_code == 200, viewer_read.text
    assert viewer_read.json()["id"] == run_id

    viewer_create = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        headers=auth_headers(viewer),
        json={
            "query": "solar revenue",
            "document_ids": [document_a.id, document_b.id],
        },
    )
    assert viewer_create.status_code == 403


def test_research_runs_list_pagination_offset(
    client: TestClient,
    db_session: Session,
):
    user = create_user(db_session, email="pagination_test_user@example.com")
    workspace_id = create_workspace(client, user, name="Pagination Workspace")
    doc = create_ready_document(db_session, user=user, filename="paper_page.pdf")

    assoc = WorkspaceDocument(workspace_id=workspace_id, document_id=doc.id, added_by=user.id)
    db_session.add(assoc)
    db_session.flush()

    from datetime import datetime, timezone

    for i in range(3):
        r = ResearchRun(
            workspace_id=workspace_id,
            requester_id=user.id,
            query=f"Pagination query {i}",
            status="completed",
            answer={"facets": {}, "markdown": f"Answer {i}"},
            run_metadata={"selected_document_ids": [doc.id]},
            created_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(r)
        db_session.flush()
        rd = ResearchRunDocument(
            research_run_id=r.id,
            document_id=doc.id,
            provenance={},
        )
        db_session.add(rd)
    db_session.commit()

    headers = auth_headers(user)
    first_page = client.get(
        f"/workspaces/{workspace_id}/research/runs?offset=0&limit=2",
        headers=headers,
    )
    second_page = client.get(
        f"/workspaces/{workspace_id}/research/runs?offset=2&limit=2",
        headers=headers,
    )

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text

    first_data = first_page.json()
    second_data = second_page.json()

    first_ids = {run["id"] for run in first_data["items"]}
    second_ids = {run["id"] for run in second_data["items"]}

    assert len(first_ids) == 2
    assert len(second_ids) >= 1
    assert first_ids.isdisjoint(second_ids)
    assert first_data["total"] == second_data["total"]
