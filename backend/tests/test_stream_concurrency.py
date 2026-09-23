from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from app.core.config import settings
from app.core.security import create_access_token
from app.core.stream_concurrency import (
    acquire_stream_lease,
    build_lease_key,
    release_stream_lease,
)
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.services.providers.errors import AIProviderError, AIProviderTimeout


class MockRedis:
    """In-memory mock reproducing Redis SET NX EX and Lua compare-and-delete."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def eval(self, script: str, numkeys: int, key: str, arg: str):
        current_val = self.store.get(key)
        if current_val == arg:
            del self.store[key]
            self.ttls.pop(key, None)
            return 1
        return 0


@pytest.fixture
def mock_redis():
    mock = MockRedis()
    with patch("app.core.stream_concurrency.get_redis_client", return_value=mock):
        yield mock


@pytest.fixture
def user_and_chat(db_session):
    import time

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Concurrency Test User",
        email=f"concurrency-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


@pytest.fixture
def second_user_and_chat(db_session):
    import time

    ts = int(time.time() * 1000) + 1
    user = UserRepository.create(
        db_session,
        name="Second Concurrency User",
        email=f"concurrency2-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# Unit Tests for Stream Concurrency Core
# ==============================================================================


@pytest.mark.asyncio
async def test_acquire_and_release_stream_lease_happy_path(mock_redis):
    """Invariant K: SET NX EX and Lua release execute correctly."""
    user_id = 100
    token = await acquire_stream_lease(user_id=user_id, client=mock_redis)
    assert token is not None
    assert mock_redis.store[build_lease_key(user_id)] == token
    assert mock_redis.ttls[build_lease_key(user_id)] == settings.AI_STREAM_LEASE_TTL_SECONDS

    released = await release_stream_lease(user_id=user_id, lease_token=token, client=mock_redis)
    assert released is True
    assert build_lease_key(user_id) not in mock_redis.store


@pytest.mark.asyncio
async def test_acquire_stream_lease_rejects_duplicate(mock_redis):
    """Invariant A & K: Rejection when lease already held."""
    user_id = 100
    token1 = await acquire_stream_lease(user_id=user_id, client=mock_redis)
    assert token1 is not None

    token2 = await acquire_stream_lease(user_id=user_id, client=mock_redis)
    assert token2 is None


@pytest.mark.asyncio
async def test_release_with_token_mismatch_fails_safely(mock_redis):
    """Invariant I: Stale worker cannot release a subsequent active lease."""
    user_id = 100
    valid_token = await acquire_stream_lease(user_id=user_id, client=mock_redis)
    stale_token = "stale_token_123"

    released = await release_stream_lease(user_id=user_id, lease_token=stale_token, client=mock_redis)
    assert released is False
    assert mock_redis.store[build_lease_key(user_id)] == valid_token


@pytest.mark.asyncio
async def test_multi_user_isolation(mock_redis):
    """Invariant C: User 1 active lease does not block User 2."""
    token_1 = await acquire_stream_lease(user_id=1, client=mock_redis)
    token_2 = await acquire_stream_lease(user_id=2, client=mock_redis)

    assert token_1 is not None
    assert token_2 is not None
    assert token_1 != token_2


@pytest.mark.asyncio
async def test_lease_ttl_configured_properly(mock_redis):
    """Invariant J: TTL is strictly positive and matches configuration."""
    user_id = 200
    token = await acquire_stream_lease(user_id=user_id, client=mock_redis)
    assert token is not None
    assert mock_redis.ttls[build_lease_key(user_id)] == settings.AI_STREAM_LEASE_TTL_SECONDS
    assert settings.AI_STREAM_LEASE_TTL_SECONDS == 180


# ==============================================================================
# Endpoint Integration & Lifecycle Invariant Tests
# ==============================================================================


def test_ai_stream_concurrency_rejection_http_429(client, user_and_chat, mock_redis):
    """Invariant A & D: Concurrent request by same user is rejected with 429 and error code."""
    user, chat = user_and_chat

    # Simulate existing active lease held by user
    mock_redis.store[build_lease_key(user.id)] = "existing_active_token"

    response = client.post(
        "/chat/stream",
        json={"chat_id": chat.id, "prompt": "Concurrent stream attempt"},
        headers=auth_headers(user),
    )

    assert response.status_code == 429
    data = response.json()
    assert data["detail"]["code"] == "AI_STREAM_CONCURRENCY_LIMIT"
    assert "already active" in data["detail"]["message"]


def test_ai_stream_early_failure_releases_lease(client, user_and_chat, mock_redis):
    """Invariant H: Pre-streaming exceptions (e.g. Chat not found) release the acquired lease."""
    user, _ = user_and_chat

    response = client.post(
        "/chat/stream",
        json={"chat_id": 999999, "prompt": "Prompt for missing chat"},
        headers=auth_headers(user),
    )

    assert response.status_code == 404
    # Lease must be cleaned up immediately, not left dangling
    assert build_lease_key(user.id) not in mock_redis.store


def test_ai_stream_lifecycle_release_on_completion(client, user_and_chat, mock_redis):
    """Invariant B & E: Normal stream completion releases the lease, permitting subsequent streams."""
    user, chat = user_and_chat

    async def mock_stream_ok(*args, **kwargs):
        yield "Hello "
        yield "world!"

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_stream_ok

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        resp1 = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "First message"},
            headers=auth_headers(user),
        )
        assert resp1.status_code == 200

        # Lease must have been released after streaming completed
        assert build_lease_key(user.id) not in mock_redis.store

        # A second stream should now succeed cleanly
        resp2 = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Second sequential message"},
            headers=auth_headers(user),
        )
        assert resp2.status_code == 200
        assert build_lease_key(user.id) not in mock_redis.store


def test_ai_stream_lifecycle_release_on_disconnect(client, user_and_chat, mock_redis):
    """Invariant F: Client disconnect or task cancellation releases the lease."""
    user, chat = user_and_chat

    async def mock_stream_disconnect(*args, **kwargs):
        yield "Token 1 "
        raise asyncio.CancelledError()

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_stream_disconnect

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Will disconnect"},
            headers=auth_headers(user),
        )

    # After disconnect, lease must be released
    assert build_lease_key(user.id) not in mock_redis.store


def test_ai_stream_lifecycle_release_on_provider_error(client, user_and_chat, mock_redis):
    """Invariant G: Provider timeouts or internal provider errors release the lease."""
    user, chat = user_and_chat

    async def mock_stream_timeout(*args, **kwargs):
        yield "Starting stream... "
        raise AIProviderTimeout("Provider timed out")

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_stream_timeout

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        resp = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Will time out"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200

    # Lease must be cleaned up in finally block
    assert build_lease_key(user.id) not in mock_redis.store


def test_ai_stream_multi_user_isolation_endpoint(
    client, user_and_chat, second_user_and_chat, mock_redis
):
    """Invariant C: User 1 active lease does not block User 2's streaming request."""
    user1, _ = user_and_chat
    user2, chat2 = second_user_and_chat

    # User 1 has an active stream lease
    mock_redis.store[build_lease_key(user1.id)] = "user1_active_lease"

    async def mock_stream_ok(*args, **kwargs):
        yield "Response for User 2"

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_stream_ok

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        resp = client.post(
            "/chat/stream",
            json={"chat_id": chat2.id, "prompt": "User 2 prompt"},
            headers=auth_headers(user2),
        )
        assert resp.status_code == 200

    # User 1 lease remains intact while User 2 lease completed cleanly
    assert mock_redis.store.get(build_lease_key(user1.id)) == "user1_active_lease"
    assert build_lease_key(user2.id) not in mock_redis.store
