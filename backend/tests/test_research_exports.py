from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.models import (
    Chat,
    Document,
    ResearchRun,
    ResearchRunDocument,
    User,
    WorkspaceDocument,
    WorkspaceMembership,
)


def create_user(
    db_session: Session,
    *,
    email: str,
) -> User:
    user = User(
        name="Research Export Test User",
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


def create_document(
    db_session: Session,
    *,
    user: User,
    filename: str,
) -> Document:
    chat = Chat(
        user_id=user.id,
        title=f"Export test chat: {filename}",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    document = Document(
        user_id=user.id,
        chat_id=chat.id,
        filename=filename,
        mime_type="application/pdf",
        status="ready",
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def add_workspace_document(
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


def create_research_run(
    db_session: Session,
    *,
    workspace_id: int,
    requester_id: int,
    status: str = "completed",
    query: str = "Compare annual solar revenue",
) -> ResearchRun:
    completed_at = datetime.now(timezone.utc) if status == "completed" else None

    answer = {
        "answer": (
            "Report A records revenue growth [C1]. "
            "Report B records an increase in production [C2]."
        ),
        "citations": [
            {
                "citation_id": "C1",
                "document_id": 1001,
                "filename": "annual-report-a.pdf",
                "chunk_id": 501,
                "page_number": 4,
                "excerpt": "Revenue increased by 12 percent during the year.",
            },
            {
                "citation_id": "C2",
                "document_id": 1002,
                "filename": "annual-report-b.pdf",
                "chunk_id": 802,
                "page_number": 9,
                "excerpt": "Production increased after the new facility opened.",
            },
        ],
    }

    run = ResearchRun(
        workspace_id=workspace_id,
        requester_id=requester_id,
        query=query,
        status=status,
        answer=answer if status == "completed" else None,
        run_metadata={
            "provider": "test-provider",
            "model": "test-model",
            "candidate_count": 4,
            "citation_count": 2,
            "selected_document_ids": [1001, 1002],
            "retrieval": {
                "strategy": "global_dense_lexical_normalized",
                "candidate_limit": 40,
            },
        },
        created_at=datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc),
        completed_at=completed_at,
        error_message="Synthetic failure for testing." if status == "failed" else None,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def create_run_with_provenance(
    db_session: Session,
    *,
    workspace_id: int,
    requester: User,
) -> tuple[ResearchRun, Document, Document]:
    document_a = create_document(
        db_session,
        user=requester,
        filename="annual-report-a.pdf",
    )
    document_b = create_document(
        db_session,
        user=requester,
        filename="annual-report-b.pdf",
    )

    add_workspace_document(
        db_session,
        workspace_id=workspace_id,
        document_id=document_a.id,
        added_by=requester.id,
    )
    add_workspace_document(
        db_session,
        workspace_id=workspace_id,
        document_id=document_b.id,
        added_by=requester.id,
    )

    answer = {
        "answer": (
            "Report A records revenue growth [C1]. "
            "Report B records an increase in production [C2]."
        ),
        "citations": [
            {
                "citation_id": "C1",
                "document_id": document_a.id,
                "filename": document_a.filename,
                "chunk_id": 501,
                "page_number": 4,
                "excerpt": "Revenue increased by 12 percent during the year.",
            },
            {
                "citation_id": "C2",
                "document_id": document_b.id,
                "filename": document_b.filename,
                "chunk_id": 802,
                "page_number": 9,
                "excerpt": "Production increased after the new facility opened.",
            },
        ],
    }

    run = ResearchRun(
        workspace_id=workspace_id,
        requester_id=requester.id,
        query="Compare annual solar revenue",
        status="completed",
        answer=answer,
        run_metadata={
            "provider": "test-provider",
            "model": "test-model",
            "candidate_count": 4,
            "citation_count": 2,
            "selected_document_ids": [document_a.id, document_b.id],
            "retrieval": {
                "strategy": "global_dense_lexical_normalized",
                "candidate_limit": 40,
            },
        },
        created_at=datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc),
        completed_at=datetime(2026, 10, 11, 10, 31, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    db_session.add_all(
        [
            ResearchRunDocument(
                research_run_id=run.id,
                document_id=document_a.id,
                provenance={
                    "filename": document_a.filename,
                    "candidate_chunks": [
                        {"chunk_id": 501, "page_number": 4, "score": 0.91},
                        {"chunk_id": 502, "page_number": 5, "score": 0.72},
                    ],
                    "citations": [answer["citations"][0]],
                },
            ),
            ResearchRunDocument(
                research_run_id=run.id,
                document_id=document_b.id,
                provenance={
                    "filename": document_b.filename,
                    "candidate_chunks": [
                        {"chunk_id": 802, "page_number": 9, "score": 0.87},
                    ],
                    "citations": [answer["citations"][1]],
                },
            ),
        ]
    )
    db_session.commit()
    db_session.refresh(run)

    return run, document_a, document_b


def test_markdown_export_contains_answer_provenance_and_bibliography(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(
        db_session,
        email="export-markdown-owner@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="Annual Research",
    )
    run, document_a, document_b = create_run_with_provenance(
        db_session,
        workspace_id=workspace_id,
        requester=owner,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=markdown",
        headers=auth_headers(owner),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "filename=" in response.headers["content-disposition"]
    assert "filename*=" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"

    body = response.text

    assert "# Research Report: Compare annual solar revenue" in body
    assert "## Synthesized Answer" in body
    assert "Report A records revenue growth [C1]." in body
    assert "## Bibliography" in body
    assert "### [C1] annual-report-a.pdf" in body
    assert "### [C2] annual-report-b.pdf" in body
    assert f"**Document ID:** {document_a.id}" in body
    assert f"**Document ID:** {document_b.id}" in body
    assert "**Chunk ID:** 501" in body
    assert "**Page:** 4" in body
    assert "Revenue increased by 12 percent during the year." in body
    assert "Production increased after the new facility opened." in body
    assert "## Reproducibility Metadata" in body
    assert '"provider": "test-provider"' in body

    assert body.index("### [C1] annual-report-a.pdf") < body.index(
        "### [C2] annual-report-b.pdf"
    )


def test_json_export_preserves_structured_provenance_and_timestamps(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(
        db_session,
        email="export-json-owner@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="Structured Research",
    )
    run, document_a, document_b = create_run_with_provenance(
        db_session,
        workspace_id=workspace_id,
        requester=owner,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=json",
        headers=auth_headers(owner),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].startswith("attachment;")

    bundle = response.json()

    assert bundle["export_schema_version"] == "1.0"

    assert bundle["workspace"]["id"] == workspace_id
    assert bundle["workspace"]["name"] == "Structured Research"
    assert bundle["workspace"]["created_by"] == owner.id

    assert bundle["research_run"]["id"] == run.id
    assert bundle["research_run"]["workspace_id"] == workspace_id
    assert bundle["research_run"]["requester_id"] == owner.id
    assert bundle["research_run"]["query"] == "Compare annual solar revenue"
    assert bundle["research_run"]["status"] == "completed"
    assert bundle["research_run"]["created_at"] == run.created_at.isoformat()
    assert bundle["research_run"]["completed_at"] == run.completed_at.isoformat()

    assert bundle["research_run"]["metadata"]["provider"] == "test-provider"
    assert bundle["answer"] == run.answer["answer"]

    bibliography = bundle["bibliography"]
    assert [item["citation_id"] for item in bibliography] == ["C1", "C2"]

    citation_a, citation_b = bibliography
    assert citation_a == {
        "citation_id": "C1",
        "document_id": document_a.id,
        "filename": document_a.filename,
        "chunk_id": 501,
        "page_number": 4,
        "excerpt": "Revenue increased by 12 percent during the year.",
    }
    assert citation_b == {
        "citation_id": "C2",
        "document_id": document_b.id,
        "filename": document_b.filename,
        "chunk_id": 802,
        "page_number": 9,
        "excerpt": "Production increased after the new facility opened.",
    }

    source_documents = bundle["source_documents"]
    assert [item["document_id"] for item in source_documents] == sorted(
        [document_a.id, document_b.id]
    )
    assert source_documents[0]["provenance"]["candidate_chunks"]
    assert source_documents[1]["provenance"]["candidate_chunks"]

    # The export is deterministic for the same completed run.
    second_response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=json",
        headers=auth_headers(owner),
    )
    assert second_response.status_code == 200
    assert second_response.content == response.content


def test_user_without_workspace_viewer_access_cannot_export(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(
        db_session,
        email="export-isolation-owner@example.test",
    )
    outsider = create_user(
        db_session,
        email="export-isolation-outsider@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="Private Research",
    )
    run, _, _ = create_run_with_provenance(
        db_session,
        workspace_id=workspace_id,
        requester=owner,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=json",
        headers=auth_headers(outsider),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found."


@pytest.mark.parametrize(
    ("run_status", "expected_status", "expected_detail"),
    [
        (
            "queued",
            409,
            "Research run cannot be exported while its status is 'queued'. "
            "Wait until the run is completed.",
        ),
        (
            "running",
            409,
            "Research run cannot be exported while its status is 'running'. "
            "Wait until the run is completed.",
        ),
        (
            "failed",
            422,
            "Failed research runs cannot be exported.",
        ),
    ],
)
def test_non_completed_research_runs_cannot_be_exported(
    client: TestClient,
    db_session: Session,
    run_status: str,
    expected_status: int,
    expected_detail: str,
):
    owner = create_user(
        db_session,
        email=f"export-status-{run_status}@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name=f"Non-completed {run_status}",
    )
    run = create_research_run(
        db_session,
        workspace_id=workspace_id,
        requester_id=owner.id,
        status=run_status,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=markdown",
        headers=auth_headers(owner),
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


def test_export_rejects_unknown_format(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(
        db_session,
        email="export-invalid-format@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="Format Validation",
    )
    run, _, _ = create_run_with_provenance(
        db_session,
        workspace_id=workspace_id,
        requester=owner,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=pdf",
        headers=auth_headers(owner),
    )

    assert response.status_code == 422


def test_export_filename_is_sanitized_and_deterministic(
    client: TestClient,
    db_session: Session,
):
    owner = create_user(
        db_session,
        email="export-filename@example.test",
    )
    workspace_id = create_workspace(
        client,
        owner,
        name="../../Sensitive Workspace / Q4",
    )
    run, _, _ = create_run_with_provenance(
        db_session,
        workspace_id=workspace_id,
        requester=owner,
    )

    response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=markdown",
        headers=auth_headers(owner),
    )

    assert response.status_code == 200

    disposition = response.headers["content-disposition"]
    match = re.search(r'filename="([^"]+)"', disposition)
    assert match is not None

    filename = match.group(1)
    assert "/" not in filename
    assert "\\" not in filename
    assert filename.endswith(".md")
    assert filename == (
        f"research-sensitive-workspace-q4-workspace-{workspace_id}" f"-run-{run.id}.md"
    )

    second_response = client.get(
        f"/workspaces/{workspace_id}/research/runs/{run.id}/export?format=markdown",
        headers=auth_headers(owner),
    )

    assert second_response.status_code == 200
    assert (
        second_response.headers["content-disposition"]
        == response.headers["content-disposition"]
    )
    assert second_response.content == response.content
