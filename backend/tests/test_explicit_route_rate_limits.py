from __future__ import annotations

import io
import time
from starlette import status
from app.repositories.user_repo import UserRepository
from app.repositories.chat_repo import ChatRepository
from app.core.security import create_access_token
from app.core.rate_limiter import limiter

def test_upload_endpoint_enforces_10_per_minute_rate_limit(client, db_session):
    limiter.enabled = True
    limiter.reset()

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

    # First 10 requests must not receive 429
    for i in range(10):
        fake_file = io.BytesIO(b"%PDF-1.4 minimal test upload")
        res = client.post(
            f"/documents/chat/{chat.id}/upload",
            files={"file": (f"test_{i}.pdf", fake_file, "application/pdf")},
            headers=headers,
        )
        assert res.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
            f"Request {i+1}/10 was unexpectedly rate-limited with status {res.status_code}: {res.text}"
        )

    # 11th request must exceed the 10/minute window and return 429
    fake_file_exceeded = io.BytesIO(b"%PDF-1.4 minimal test upload")
    res_exceeded = client.post(
        f"/documents/chat/{chat.id}/upload",
        files={"file": ("test_exceeded.pdf", fake_file_exceeded, "application/pdf")},
        headers=headers,
    )
    assert res_exceeded.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
        f"11th upload request expected 429, but got {res_exceeded.status_code}: {res_exceeded.text}"
    )

def test_research_run_endpoint_enforces_5_per_minute_rate_limit(client, db_session):
    limiter.enabled = True
    limiter.reset()

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

    # First 5 requests must not receive 429
    for i in range(5):
        res = client.post(
            f"/workspaces/{workspace_id}/research/runs",
            json={
                "query": "Synthesize security and rate limit considerations",
                "document_ids": [101, 102],
            },
            headers=headers,
        )
        assert res.status_code != status.HTTP_429_TOO_MANY_REQUESTS, (
            f"Request {i+1}/5 was unexpectedly rate-limited with status {res.status_code}: {res.text}"
        )

    # 6th request must exceed the 5/minute window and return 429
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
