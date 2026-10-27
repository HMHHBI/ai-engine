"""
Comprehensive Security & IDOR Authorization Matrix (Phase 2C / PR 3).

Validates server-side authorization enforcement across Research, Workspace,
and Document APIs:
1. Workspace boundary isolation and resource non-disclosure (404 on unjoined workspaces,
   zero leakage of query, answer, or citation sentinel tokens in response bodies).
2. Cross-workspace Run ID and Export IDOR prevention with body inspection.
3. Multi-document research synthesis foreign document injection guards with database
   side-effect / mutation verification.
4. Role-based access control (RBAC) boundaries (viewer vs. researcher vs. admin/owner)
   including document attachment and synthesis creation.
5. Document metadata, file-stream download, and retry/delete cross-tenant protection.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

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
    Workspace,
    WorkspaceDocument,
    WorkspaceMembership,
)
from app.services.embedding_service import EmbeddingService
from app.services.providers.factory import LLMProviderFactory


class MockLLMProvider:
    async def generate_response(self, *args, **kwargs) -> str:
        return json.dumps({
            "facets": {
                "methodology": "Mock methodology [C1] [C2].",
                "datasets": "Mock datasets [C1].",
                "metrics": "Mock metrics [C2].",
                "findings": "Mock findings [C1] [C2].",
                "limitations": "Mock limitations [C2].",
            },
            "citations": ["C1", "C2"],
        })

    async def generate_stream(self, *args, **kwargs):
        if False:
            yield ""


@pytest.fixture()
def mock_providers(monkeypatch):
    monkeypatch.setattr(
        EmbeddingService,
        "generate_embedding",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        LLMProviderFactory,
        "get_provider",
        lambda *args, **kwargs: MockLLMProvider(),
    )


def create_user_fixture(db_session: Session, email: str, name: str = "Test User") -> User:
    user = User(
        name=name,
        email=email,
        password="test-password-hash",
        is_active=True,
        token_version=1,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


def create_workspace_fixture(
    db_session: Session,
    *,
    owner: User,
    name: str = "Secure Workspace",
) -> Workspace:
    ws = Workspace(name=name, created_by=owner.id)
    db_session.add(ws)
    db_session.commit()
    db_session.refresh(ws)

    membership = WorkspaceMembership(
        workspace_id=ws.id,
        user_id=owner.id,
        role="owner",
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return ws


def add_workspace_member(
    db_session: Session,
    *,
    workspace_id: int,
    user: User,
    role: str,
) -> WorkspaceMembership:
    membership = WorkspaceMembership(
        workspace_id=workspace_id,
        user_id=user.id,
        role=role,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def create_document_fixture(
    db_session: Session,
    *,
    user: User,
    filename: str,
    status: str = "ready",
    storage_key: str | None = None,
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
        storage_key=storage_key or f"uploads/{user.id}/{filename}",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    chunk = DocumentChunk(
        chat_id=chat.id,
        document_id=doc.id,
        content=f"Benchmark content for {filename}",
        page_number=1,
        chunk_index=0,
        embedding=None,
    )
    db_session.add(chunk)
    db_session.commit()
    return doc


def associate_document_to_ws(
    db_session: Session,
    *,
    workspace_id: int,
    document_id: int,
    added_by: int,
) -> WorkspaceDocument:
    wd = WorkspaceDocument(
        workspace_id=workspace_id,
        document_id=document_id,
        added_by=added_by,
    )
    db_session.add(wd)
    db_session.commit()
    db_session.refresh(wd)
    return wd


def create_research_run_fixture(
    db_session: Session,
    *,
    workspace_id: int,
    requester_id: int,
    doc_ids: list[int],
    sentinel_suffix: str = "DEFAULT",
) -> tuple[ResearchRun, dict[str, str]]:
    sentinels = {
        "query": f"SENTINEL_QUERY_{sentinel_suffix}_TOP_SECRET",
        "answer": f"SENTINEL_ANSWER_{sentinel_suffix}_CONFIDENTIAL",
        "facet": f"SENTINEL_METHODOLOGY_{sentinel_suffix}_INTERNAL",
        "excerpt": f"SENTINEL_EXCERPT_{sentinel_suffix}_RESTRICTED_EVIDENCE",
    }

    run = ResearchRun(
        workspace_id=workspace_id,
        requester_id=requester_id,
        query=sentinels["query"],
        status="completed",
        answer=f"{sentinels['answer']} [C1] [C2].",
        run_metadata={
            "facets": {
                "methodology": f"Comparative methodology {sentinels['facet']}.",
                "datasets": "Dataset benchmarks.",
                "metrics": "F1 score.",
                "findings": "Significant findings.",
                "limitations": "Known limitations.",
            },
            "citations": [
                {
                    "marker": "[C1]",
                    "chunk_id": 1,
                    "document_id": doc_ids[0] if doc_ids else 1,
                    "filename": "doc_1.pdf",
                    "page_number": 1,
                    "excerpt": sentinels["excerpt"],
                },
                {
                    "marker": "[C2]",
                    "chunk_id": 2,
                    "document_id": doc_ids[1] if len(doc_ids) > 1 else 1,
                    "filename": "doc_2.pdf",
                    "page_number": 1,
                    "excerpt": "Evidence text 2",
                },
            ],
        },
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    for did in doc_ids:
        rrd = ResearchRunDocument(research_run_id=run.id, document_id=did)
        db_session.add(rrd)
    db_session.commit()
    return run, sentinels


# =========================================================================
# Scenario 1: Cross-Workspace IDOR (Run Retrieval & Export Isolation)
# =========================================================================

def test_cross_workspace_run_retrieval_idor_denied(
    client: TestClient,
    db_session: Session,
):
    """
    Ensure user in Workspace A cannot access or discover runs belonging to Workspace B,
    even if the Run ID is guessed or known. Inspects serialized response to ensure
    no confidential sentinels from Workspace B are leaked.
    """
    owner_a = create_user_fixture(db_session, "owner-a@security.test")
    owner_b = create_user_fixture(db_session, "owner-b@security.test")

    ws_a = create_workspace_fixture(db_session, owner=owner_a, name="Workspace A")
    ws_b = create_workspace_fixture(db_session, owner=owner_b, name="Workspace B")

    doc_b1 = create_document_fixture(db_session, user=owner_b, filename="sensitive_b1.pdf")
    doc_b2 = create_document_fixture(db_session, user=owner_b, filename="sensitive_b2.pdf")
    associate_document_to_ws(db_session, workspace_id=ws_b.id, document_id=doc_b1.id, added_by=owner_b.id)
    associate_document_to_ws(db_session, workspace_id=ws_b.id, document_id=doc_b2.id, added_by=owner_b.id)

    run_b, sentinels = create_research_run_fixture(
        db_session,
        workspace_id=ws_b.id,
        requester_id=owner_b.id,
        doc_ids=[doc_b1.id, doc_b2.id],
        sentinel_suffix="RUN_GET",
    )

    # 1. User A queries Run B under Workspace A ID -> 404 (Scoped to workspace_id)
    res = client.get(
        f"/workspaces/{ws_a.id}/research/runs/{run_b.id}",
        headers=auth_header(owner_a),
    )
    assert res.status_code == 404
    assert "not found" in res.json().get("detail", "").lower()
    for sentinel_value in sentinels.values():
        assert sentinel_value not in res.text

    # 2. User A queries Run B under Workspace B ID directly -> 404 (Non-member rejection)
    res_direct = client.get(
        f"/workspaces/{ws_b.id}/research/runs/{run_b.id}",
        headers=auth_header(owner_a),
    )
    assert res_direct.status_code == 404
    assert res_direct.json().get("detail") == "Workspace not found."
    for sentinel_value in sentinels.values():
        assert sentinel_value not in res_direct.text


def test_cross_workspace_run_export_idor_denied(
    client: TestClient,
    db_session: Session,
):
    """
    Verify unauthorized users cannot trigger or download run exports (JSON / Markdown)
    for runs in workspaces they do not belong to. Asserts absence of sentinel data
    in response bodies.
    """
    owner_a = create_user_fixture(db_session, "owner-export-a@security.test")
    owner_b = create_user_fixture(db_session, "owner-export-b@security.test")

    ws_a = create_workspace_fixture(db_session, owner=owner_a, name="Workspace A")
    ws_b = create_workspace_fixture(db_session, owner=owner_b, name="Workspace B")

    doc_b1 = create_document_fixture(db_session, user=owner_b, filename="confidential_b1.pdf")
    doc_b2 = create_document_fixture(db_session, user=owner_b, filename="confidential_b2.pdf")
    associate_document_to_ws(db_session, workspace_id=ws_b.id, document_id=doc_b1.id, added_by=owner_b.id)
    associate_document_to_ws(db_session, workspace_id=ws_b.id, document_id=doc_b2.id, added_by=owner_b.id)

    run_b, sentinels = create_research_run_fixture(
        db_session,
        workspace_id=ws_b.id,
        requester_id=owner_b.id,
        doc_ids=[doc_b1.id, doc_b2.id],
        sentinel_suffix="RUN_EXPORT",
    )

    for fmt in ("json", "markdown"):
        # Access via Workspace A route
        res_a = client.get(
            f"/workspaces/{ws_a.id}/research/runs/{run_b.id}/export?format={fmt}",
            headers=auth_header(owner_a),
        )
        assert res_a.status_code == 404
        assert "not found" in res_a.json().get("detail", "").lower()
        for sentinel_value in sentinels.values():
            assert sentinel_value not in res_a.text

        # Direct access via Workspace B route without membership
        res_b = client.get(
            f"/workspaces/{ws_b.id}/research/runs/{run_b.id}/export?format={fmt}",
            headers=auth_header(owner_a),
        )
        assert res_b.status_code == 404
        assert res_b.json().get("detail") == "Workspace not found."
        for sentinel_value in sentinels.values():
            assert sentinel_value not in res_b.text


def test_cross_workspace_run_list_non_member_denied(
    client: TestClient,
    db_session: Session,
):
    """
    Ensure non-members cannot list runs of a workspace.
    """
    owner_b = create_user_fixture(db_session, "owner-list-b@security.test")
    outsider = create_user_fixture(db_session, "outsider@security.test")
    ws_b = create_workspace_fixture(db_session, owner=owner_b, name="Workspace B")

    res = client.get(
        f"/workspaces/{ws_b.id}/research/runs",
        headers=auth_header(outsider),
    )
    assert res.status_code == 404
    assert res.json().get("detail") == "Workspace not found."


# =========================================================================
# Scenario 2: Multi-Document Synthesis Injection Boundary & Side-Effect Check
# =========================================================================

def test_synthesis_rejects_foreign_and_unassociated_documents(
    client: TestClient,
    db_session: Session,
    mock_providers,
):
    """
    Ensure POST /workspaces/{workspace_id}/research/runs rejects foreign document IDs:
    - Documents belonging to other users.
    - Documents owned by caller but not associated with the target workspace.
    Verifies that rejected requests cause zero database mutations (no ResearchRun
    or ResearchRunDocument records created).
    """
    user_a = create_user_fixture(db_session, "user-synth-a@security.test")
    user_b = create_user_fixture(db_session, "user-synth-b@security.test")

    ws_a = create_workspace_fixture(db_session, owner=user_a, name="Synth WS A")
    ws_other = create_workspace_fixture(db_session, owner=user_a, name="Synth WS Other")

    doc_valid = create_document_fixture(db_session, user=user_a, filename="valid_doc.pdf")
    associate_document_to_ws(db_session, workspace_id=ws_a.id, document_id=doc_valid.id, added_by=user_a.id)

    # 1. Foreign user document
    doc_foreign = create_document_fixture(db_session, user=user_b, filename="foreign_doc.pdf")

    runs_before = db_session.query(ResearchRun).count()
    run_docs_before = db_session.query(ResearchRunDocument).count()

    res_foreign = client.post(
        f"/workspaces/{ws_a.id}/research/runs",
        headers=auth_header(user_a),
        json={
            "query": "synthesis query",
            "document_ids": [doc_valid.id, doc_foreign.id],
        },
    )
    assert res_foreign.status_code in (400, 404, 422)

    db_session.expire_all()
    assert db_session.query(ResearchRun).count() == runs_before, "ResearchRun created on rejected foreign doc"
    assert db_session.query(ResearchRunDocument).count() == run_docs_before, "ResearchRunDocument created on rejected foreign doc"

    # 2. Document owned by User A but associated only with ws_other
    doc_other_ws = create_document_fixture(db_session, user=user_a, filename="other_ws_doc.pdf")
    associate_document_to_ws(db_session, workspace_id=ws_other.id, document_id=doc_other_ws.id, added_by=user_a.id)

    runs_before_cross = db_session.query(ResearchRun).count()
    run_docs_before_cross = db_session.query(ResearchRunDocument).count()

    res_other = client.post(
        f"/workspaces/{ws_a.id}/research/runs",
        headers=auth_header(user_a),
        json={
            "query": "synthesis query",
            "document_ids": [doc_valid.id, doc_other_ws.id],
        },
    )
    assert res_other.status_code in (400, 404, 422)

    db_session.expire_all()
    assert db_session.query(ResearchRun).count() == runs_before_cross, "ResearchRun created on unassociated workspace doc"
    assert db_session.query(ResearchRunDocument).count() == run_docs_before_cross, "ResearchRunDocument created on unassociated workspace doc"


# =========================================================================
# Scenario 3: Role-Based Authorization Enforcement (RBAC)
# =========================================================================

def test_workspace_role_hierarchy_permissions(
    client: TestClient,
    db_session: Session,
    mock_providers,
):
    """
    Test role levels:
    - viewer (level 1): Can read runs and docs, CANNOT start research runs, CANNOT attach documents.
    - researcher (level 2): Can read and start research runs, CANNOT delete workspace.
    Verifies that unauthorized mutations leave no side effects in the database.
    """
    owner = create_user_fixture(db_session, "owner-rbac@security.test")
    viewer = create_user_fixture(db_session, "viewer-rbac@security.test")
    researcher = create_user_fixture(db_session, "researcher-rbac@security.test")

    ws = create_workspace_fixture(db_session, owner=owner, name="RBAC Workspace")
    add_workspace_member(db_session, workspace_id=ws.id, user=viewer, role="viewer")
    add_workspace_member(db_session, workspace_id=ws.id, user=researcher, role="researcher")

    doc1 = create_document_fixture(db_session, user=owner, filename="doc_rbac_1.pdf")
    doc2 = create_document_fixture(db_session, user=owner, filename="doc_rbac_2.pdf")
    associate_document_to_ws(db_session, workspace_id=ws.id, document_id=doc1.id, added_by=owner.id)
    associate_document_to_ws(db_session, workspace_id=ws.id, document_id=doc2.id, added_by=owner.id)

    # Document to test attachment permissions
    doc_unattached = create_document_fixture(db_session, user=viewer, filename="viewer_unattached.pdf")

    # 1. Viewer CAN read documents and runs
    res_view_docs = client.get(f"/workspaces/{ws.id}/documents", headers=auth_header(viewer))
    assert res_view_docs.status_code == 200

    res_view_runs = client.get(f"/workspaces/{ws.id}/research/runs", headers=auth_header(viewer))
    assert res_view_runs.status_code == 200

    # 2. Viewer CANNOT attach documents to workspace (requires researcher/admin role)
    ws_docs_before = db_session.query(WorkspaceDocument).filter(WorkspaceDocument.workspace_id == ws.id).count()
    res_viewer_attach = client.post(
        f"/workspaces/{ws.id}/documents",
        headers=auth_header(viewer),
        json={"document_id": doc_unattached.id},
    )
    assert res_viewer_attach.status_code == 403
    assert "insufficient workspace permissions" in res_viewer_attach.json().get("detail", "").lower()

    db_session.expire_all()
    ws_docs_after = db_session.query(WorkspaceDocument).filter(WorkspaceDocument.workspace_id == ws.id).count()
    assert ws_docs_after == ws_docs_before, "WorkspaceDocument created by unauthorized viewer"

    # 3. Viewer CANNOT trigger synthesis (requires researcher role)
    runs_before = db_session.query(ResearchRun).filter(ResearchRun.workspace_id == ws.id).count()
    res_viewer_synth = client.post(
        f"/workspaces/{ws.id}/research/runs",
        headers=auth_header(viewer),
        json={"query": "test query", "document_ids": [doc1.id, doc2.id]},
    )
    assert res_viewer_synth.status_code == 403
    assert "insufficient workspace permissions" in res_viewer_synth.json().get("detail", "").lower()

    db_session.expire_all()
    assert db_session.query(ResearchRun).filter(ResearchRun.workspace_id == ws.id).count() == runs_before

    # 4. Researcher CAN trigger synthesis with valid multi-document set
    res_researcher_synth = client.post(
        f"/workspaces/{ws.id}/research/runs",
        headers=auth_header(researcher),
        json={"query": "test query", "document_ids": [doc1.id, doc2.id]},
    )
    assert res_researcher_synth.status_code == 201

    # 5. Researcher CANNOT delete workspace (requires admin/owner)
    res_researcher_delete = client.delete(
        f"/workspaces/{ws.id}",
        headers=auth_header(researcher),
    )
    assert res_researcher_delete.status_code == 403


# =========================================================================
# Scenario 4: Document Metadata, File Download & Storage Protection
# =========================================================================

def test_document_metadata_and_file_download_idor_denied(
    client: TestClient,
    db_session: Session,
):
    """
    Ensure documents owned by User B cannot be accessed, downloaded,
    retried, or deleted by User A.
    """
    user_a = create_user_fixture(db_session, "user-doc-a@security.test")
    user_b = create_user_fixture(db_session, "user-doc-b@security.test")

    doc_b = create_document_fixture(
        db_session,
        user=user_b,
        filename="private_file_b.pdf",
        status="ready",
        storage_key="secure_keys/doc_b.pdf",
    )

    # 1. Metadata GET
    res_meta = client.get(f"/documents/{doc_b.id}", headers=auth_header(user_a))
    assert res_meta.status_code == 404
    assert "unauthorized" in res_meta.json().get("detail", "").lower() or "not found" in res_meta.json().get("detail", "").lower()

    # 2. File Download GET -> must return 404 without storage access
    with patch("app.api.documents.get_storage_backend") as mock_storage:
        res_file = client.get(f"/documents/{doc_b.id}/file", headers=auth_header(user_a))
        assert res_file.status_code == 404
        mock_storage.assert_not_called()

    # 3. Patch Document
    res_patch = client.patch(
        f"/documents/{doc_b.id}",
        headers=auth_header(user_a),
        json={"filename": "tampered.pdf"},
    )
    assert res_patch.status_code == 404

    # 4. Delete Document -> must return 404 without invoking storage delete
    with patch("app.api.documents.get_storage_backend") as mock_storage:
        res_del = client.delete(f"/documents/{doc_b.id}", headers=auth_header(user_a))
        assert res_del.status_code == 404
        mock_storage.assert_not_called()

    # 5. Retry Document
    res_retry = client.post(f"/documents/{doc_b.id}/retry", headers=auth_header(user_a))
    assert res_retry.status_code == 404
