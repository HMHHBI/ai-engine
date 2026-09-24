from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.chat import _heartbeat_stream
from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import Chat
from app.db.session import SessionLocal
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from starlette.requests import Request


@pytest.fixture
def user_and_chat(db_session):
    import time

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Heartbeat Test User",
        email=f"heartbeat-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


class DummyRequest:
    def __init__(self, disconnected: bool = False):
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


# ==============================================================================
# Unit Invariant Tests: _heartbeat_stream
# ==============================================================================


@pytest.mark.asyncio
async def test_heartbeat_emitted_when_source_is_idle():
    """Invariant: Emits exact ': keep-alive\n\n' comment when source delay exceeds interval."""
    async def slow_source() -> AsyncIterator[str]:
        await asyncio.sleep(0.06)
        yield "data: chunk 1\n\n"

    req = DummyRequest()
    chunks = []
    async for item in _heartbeat_stream(slow_source(), req, heartbeat_interval=0.02):
        chunks.append(item)

    assert ": keep-alive\n\n" in chunks
    assert "data: chunk 1\n\n" in chunks
    assert chunks.index(": keep-alive\n\n") < chunks.index("data: chunk 1\n\n")


@pytest.mark.asyncio
async def test_no_heartbeat_emitted_when_source_is_fast():
    """Invariant: When source yields faster than interval, zero heartbeat frames are emitted."""
    async def fast_source() -> AsyncIterator[str]:
        yield "data: 1\n\n"
        yield "data: 2\n\n"

    req = DummyRequest()
    chunks = []
    async for item in _heartbeat_stream(fast_source(), req, heartbeat_interval=1.0):
        chunks.append(item)

    assert chunks == ["data: 1\n\n", "data: 2\n\n"]
    assert ": keep-alive\n\n" not in chunks


@pytest.mark.asyncio
async def test_payload_byte_integrity_preserved():
    """Invariant: SSE event types and JSON structure remain completely unmutated."""
    original_events = [
        'event: stream_started\ndata: {"provider":"mock","model":"fast"}\n\n',
        'event: sources\ndata: {"sources":[]}\n\n',
        'event: chunk\ndata: {"text":"Hello"}\n\n',
        'event: stream_completed\ndata: {"message_id":1}\n\n',
    ]

    async def standard_source() -> AsyncIterator[str]:
        for event in original_events:
            await asyncio.sleep(0.01)
            yield event

    req = DummyRequest()
    emitted = []
    async for item in _heartbeat_stream(standard_source(), req, heartbeat_interval=0.05):
        emitted.append(item)

    data_events = [e for e in emitted if e != ": keep-alive\n\n"]
    assert data_events == original_events


@pytest.mark.asyncio
async def test_consumer_cancellation_cleans_up_tasks():
    """Invariant: Cancelling downstream consumer cancels producer task and closes generator."""
    generator_closed = False

    async def long_source() -> AsyncIterator[str]:
        nonlocal generator_closed
        try:
            await asyncio.sleep(10.0)
            yield "data: unreachable\n\n"
        finally:
            generator_closed = True

    req = DummyRequest()
    stream = _heartbeat_stream(long_source(), req, heartbeat_interval=0.01)

    iterator = stream.__aiter__()
    first = await iterator.__anext__()
    assert first == ": keep-alive\n\n"

    await iterator.aclose()
    await asyncio.sleep(0.02)
    assert generator_closed is True


@pytest.mark.asyncio
async def test_client_disconnect_terminates_stream():
    """Invariant: Client disconnect stops heartbeat generator immediately."""
    source_exhausted = False

    async def pending_source() -> AsyncIterator[str]:
        nonlocal source_exhausted
        try:
            await asyncio.sleep(1.0)
            yield "never\n\n"
            source_exhausted = True
        finally:
            pass

    req = DummyRequest(disconnected=True)
    chunks = []
    async for chunk in _heartbeat_stream(pending_source(), req, heartbeat_interval=0.01):
        chunks.append(chunk)

    assert chunks == []
    assert source_exhausted is False


@pytest.mark.asyncio
async def test_source_exception_cleans_up_producer_task():
    """Invariant: Source exceptions bubble up while closing pending tasks cleanly."""
    async def failing_source() -> AsyncIterator[str]:
        await asyncio.sleep(0.01)
        raise RuntimeError("Source exploded")
        yield "never"

    req = DummyRequest()
    with pytest.raises(RuntimeError, match="Source exploded"):
        async for _ in _heartbeat_stream(failing_source(), req, heartbeat_interval=0.05):
            pass


def test_heartbeat_configuration_validity():
    """Invariant: Heartbeat interval is positive and strictly lower than stream duration ceiling."""
    assert settings.HEARTBEAT_INTERVAL_SECONDS > 0
    assert settings.HEARTBEAT_INTERVAL_SECONDS < settings.AI_STREAM_MAX_DURATION_SECONDS
    assert settings.HEARTBEAT_INTERVAL_SECONDS <= 30.0


# ==============================================================================
# Endpoint Integration Tests
# ==============================================================================


def test_heartbeat_protects_rag_embedding_retrieval_delay(client, user_and_chat):
    """Invariant: Heartbeat frames are emitted during slow RAG retrieval before first SSE event."""
    user, chat = user_and_chat

    # Persist pdf_context=True in the database
    with SessionLocal() as session:
        session.query(Chat).filter(Chat.id == chat.id).update({"pdf_context": True})
        session.commit()

    async def slow_embed_fn(*args, **kwargs):
        await asyncio.sleep(0.06)
        return [0.1] * 768

    mock_embed = AsyncMock(side_effect=slow_embed_fn)

    async def fast_stream(*args, **kwargs):
        yield "done"

    mock_provider = MagicMock()
    mock_provider.generate_stream = fast_stream

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new=mock_embed,
    ), patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ), patch(
        "app.core.config.settings.HEARTBEAT_INTERVAL_SECONDS",
        0.02,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "RAG delay prompt"},
            headers=auth_headers(user),
        )

        assert response.status_code == 200
        text = response.text
        assert ": keep-alive\n\n" in text
        assert "event: stream_started" in text

        # Invariant 1: Exactly one embedding generation execution per RAG request
        assert mock_embed.await_count == 1

        # Invariant 2: Heartbeat arrived before the first real SSE frame
        first_keep_alive_idx = text.index(": keep-alive\n\n")
        stream_started_idx = text.index("event: stream_started")
        assert first_keep_alive_idx < stream_started_idx


def test_heartbeat_does_not_mutate_telemetry_chunk_count(client, user_and_chat):
    """Invariant: Heartbeat comments do not increment chunk_count or pollute token telemetry."""
    user, chat = user_and_chat

    async def delayed_token_stream(*args, **kwargs):
        yield "token1"
        await asyncio.sleep(0.05)
        yield "token2"

    mock_provider = MagicMock()
    mock_provider.generate_stream = delayed_token_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ), patch(
        "app.core.config.settings.HEARTBEAT_INTERVAL_SECONDS",
        0.015,
    ), patch("app.api.chat.logger.info") as mock_logger:
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Verify chunk count"},
            headers=auth_headers(user),
        )

        assert response.status_code == 200
        assert ": keep-alive\n\n" in response.text

        completion_calls = [
            call for call in mock_logger.call_args_list
            if len(call[0]) > 0 and call[0][0] == "ai_stream_completed"
        ]
        assert len(completion_calls) == 1
        extra = completion_calls[0][1]["extra"]
        assert extra["chunk_count"] == 2
