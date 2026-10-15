from __future__ import annotations

import io
import time
import pytest
from starlette import status
from app.repositories.user_repo import UserRepository
from app.repositories.chat_repo import ChatRepository
from app.core.security import create_access_token
from app.core.rate_limiter import limiter

VALID_TEXT_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 44>>stream\n"
    b"BT\n"
    b"/Helvetica 12 Tf\n"
    b"100 700 Td\n"
    b"(Hello World) Tj\n"
    b"ET\n"
    b"endstream\n"
    b"endobj\n"
    b"xref\n"
    b"0 5\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000052 00000 n \n"
    b"0000000101 00000 n \n"
    b"0000000192 00000 n \n"
    b"trailer<</Size 5/Root 1 0 R>>\n"
    b"startxref\n"
    b"285\n"
    b"%%EOF\n"
)

@pytest.fixture
def enabled_isolated_limiter():
    original_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield limiter
    finally:
        limiter.reset()
        limiter.enabled = original_enabled

def test_upload_endpoint_enforces_10_per_minute_rate_limit(
    client, db_session, enabled_isolated_limiter, monkeypatch
):
    async def mock_process_job(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.documents.DocumentLifecycleService.process_job",
        mock_process_job,
    )

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Upload Rate Limit User",
        email=f"ratelimit-upload-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)

    token = create_access_token(user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}

    # First 10 requests: must succeed with 201 Created
    for i in range(10):
        fake_file = io.BytesIO(VALID_TEXT_PDF)
        res = client.post(
            f"/documents/chat/{chat.id}/upload",
            files={"file": (f"valid_doc_{i}.pdf", fake_file, "application/pdf")},
            headers=headers,
        )
        assert res.status_code == status.HTTP_201_CREATED, (
            f"Request {i+1}/10 failed with status {res.status_code}: {res.text}"
        )

    # 11th request: must exceed the 10/minute window and return 429
    fake_file_exceeded = io.BytesIO(VALID_TEXT_PDF)
    res_exceeded = client.post(
        f"/documents/chat/{chat.id}/upload",
        files={"file": ("valid_doc_exceeded.pdf", fake_file_exceeded, "application/pdf")},
        headers=headers,
    )
    assert res_exceeded.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
        f"11th upload request expected 429, but got {res_exceeded.status_code}: {res_exceeded.text}"
    )

def test_research_run_endpoint_enforces_5_per_minute_rate_limit(
    client, db_session, enabled_isolated_limiter, monkeypatch
):
    async def mock_retrieve(*args, **kwargs):
        return []

    async def mock_synthesize(*args, **kwargs):
        return {
            "answer": "Rate limit verification answer",
            "citations": [],
            "evidence": [],
            "provider": "ollama",
            "model": "deepseek-r1:8b",
        }

    def mock_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.api.research.retrieve_multi_document_candidates",
        mock_retrieve,
    )
    monkeypatch.setattr(
        "app.api.research.synthesize_research_answer",
        mock_synthesize,
    )
    monkeypatch.setattr(
        "app.api.research._persist_document_provenance",
        mock_persist,
    )

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Research Rate Limit User",
        email=f"ratelimit-research-{ts}@example.com",
        password="Password!123",
    )
    token = create_access_token(user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}

    ws_res = client.post(
        "/workspaces/",
        headers=headers,
        json={"name": f"Workspace {ts}"},
    )
    assert ws_res.status_code == status.HTTP_201_CREATED, ws_res.text
    workspace_id = ws_res.json()["id"]

    # First 5 requests: allowed within quota, must strictly succeed with 201 Created
    for i in range(5):
        res = client.post(
            f"/workspaces/{workspace_id}/research/runs",
            json={
                "query": "Synthesize security and rate limit considerations",
                "document_ids": [101, 102],
            },
            headers=headers,
        )
        assert res.status_code == status.HTTP_201_CREATED, (
            f"Request {i+1}/5 failed with unexpected status {res.status_code}: {res.text}"
        )

    # 6th request: must exceed the 5/minute window and return 429
    res_exceeded = client.post(
        f"/workspaces/{workspace_id}/research/runs",
        json={
            "query": "Synthesize security and rate limit considerations",
            "document_ids": [101, 102],
        },
        headers=headers,
    )
    assert res_exceeded.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
        f"6th research run request expected 429, but got {res_exceeded.status_code}: {res_exceeded.text}"
    )
