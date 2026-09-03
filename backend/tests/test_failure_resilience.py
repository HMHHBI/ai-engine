from __future__ import annotations

import time
from unittest.mock import patch
import pytest
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def user_and_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Resilience Tester",
        email=f"resilience-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def test_database_recovery_lifecycle_without_restart(client, user_and_chat):
    user, _ = user_and_chat

    # 1. Healthy state
    assert client.get("/health/live").status_code == 200
    with patch("app.api.health._check_redis", return_value=True):
        ready_init = client.get("/health/ready")
        assert ready_init.status_code == 200
        assert ready_init.json()["checks"]["database"] == "ok"

    # 2. Injected DB failure
    with patch(
        "app.api.health.engine.connect",
        side_effect=OperationalError("connection refused", {}, None),
    ):
        live_during_failure = client.get("/health/live")
        assert live_during_failure.status_code == 200
        assert live_during_failure.json() == {"status": "ok"}

        with patch("app.api.health._check_redis", return_value=True):
            ready_during_failure = client.get("/health/ready")
            assert ready_during_failure.status_code == 503
            assert ready_during_failure.json()["status"] == "not_ready"
            assert ready_during_failure.json()["checks"]["database"] == "error"

    # 3. Restored DB state without restarting container/app
    with patch("app.api.health._check_redis", return_value=True):
        ready_restored = client.get("/health/ready")
        assert ready_restored.status_code == 200
        assert ready_restored.json()["checks"]["database"] == "ok"

    # 4. Normal operation resumes cleanly
    new_chat = ChatRepository.create_chat(user_id=user.id, title="Post-Recovery Chat")
    assert new_chat.id is not None
    assert new_chat.title == "Post-Recovery Chat"


def test_redis_recovery_lifecycle_without_restart(client):
    # 1. Healthy initial state
    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=True
    ):
        ready_init = client.get("/health/ready")
        assert ready_init.status_code == 200
        assert ready_init.json()["checks"]["redis"] == "ok"

    # 2. Redis failure injected
    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=False
    ):
        live_res = client.get("/health/live")
        assert live_res.status_code == 200
        assert live_res.json() == {"status": "ok"}

        ready_down = client.get("/health/ready")
        assert ready_down.status_code == 503
        assert ready_down.json()["status"] == "not_ready"
        assert ready_down.json()["checks"]["redis"] == "error"

    # 3. Redis restored without restart
    with patch("app.api.health._check_database", return_value=True), patch(
        "app.api.health._check_redis", return_value=True
    ):
        ready_restored = client.get("/health/ready")
        assert ready_restored.status_code == 200
        assert ready_restored.json()["status"] == "ready"
        assert ready_restored.json()["checks"]["redis"] == "ok"


def test_chat_turn_db_failure_rolls_back_and_subsequent_turn_succeeds(
    client, user_and_chat
):
    user, _ = user_and_chat
    token = create_access_token(user_id=user.id)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 1. Simulate DB failure during chat creation
    with patch(
        "app.repositories.chat_repo.ChatRepository.create_chat",
        side_effect=OperationalError("connection terminated unexpectedly", {}, None),
    ):
        response = client.post(
            "/chat/new",
            headers=auth_headers,
        )
        assert response.status_code == 500
        assert "connection terminated" not in response.text.lower()
        assert "traceback" not in response.text.lower()
        assert "x-correlation-id" in [k.lower() for k in response.headers.keys()]

    # 2. Subsequent request succeeds once DB is unblocked/restored
    success_res = client.post(
        "/chat/new",
        headers=auth_headers,
    )
    assert success_res.status_code in (200, 201)
    data = success_res.json()
    assert "chat_id" in data or "id" in data
