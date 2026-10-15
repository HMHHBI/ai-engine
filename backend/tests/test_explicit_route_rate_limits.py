from __future__ import annotations

import io
import time
from starlette import status
from app.repositories.user_repo import UserRepository
from app.repositories.chat_repo import ChatRepository
from app.core.security import create_access_token

def test_upload_endpoint_enforces_10_per_minute_rate_limit(client, db_session):
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

    responses = []
    hit_429 = False

    for i in range(15):
        fake_file = io.BytesIO(b"%PDF-1.4 sample payload content")
        res = client.post(
            f"/documents/chat/{chat.id}/upload",
            files={"file": (f"test_{i}.pdf", fake_file, "application/pdf")},
            headers=headers,
        )
        responses.append(res.status_code)
        if res.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            hit_429 = True
            break

    assert hit_429, f"Expected 429 Too Many Requests, got statuses: {responses}"

def test_research_run_endpoint_enforces_5_per_minute_rate_limit(client, db_session):
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

    responses = []
    hit_429 = False

    for i in range(8):
        res = client.post(
            f"/workspaces/{workspace_id}/research/runs",
            json={
                "query": "Synthesize security and rate limit considerations",
                "document_ids": [101, 102],
            },
            headers=headers,
        )
        responses.append(res.status_code)
        if res.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            hit_429 = True
            break

    assert hit_429, f"Expected 429 Too Many Requests, got statuses: {responses}"
