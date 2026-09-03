from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.services.providers.errors import (
    AIProviderTimeout,
    AIProviderUnavailable,
)
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.openai_provider import OpenAIProvider


@pytest.fixture()
def user_and_chat(db_session):
    import time

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Timeout Test User",
        email=f"timeout-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def parse_sse_events(response_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []

    for raw_event in response_text.split("\n\n"):
        raw_event = raw_event.strip()

        if not raw_event:
            continue

        event_name = None
        data_lines: list[str] = []

        for line in raw_event.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())

        if event_name is None:
            continue

        data = json.loads("\n".join(data_lines))
        events.append((event_name, data))

    return events


@pytest.mark.asyncio
async def test_ollama_connect_timeout_raises_provider_timeout():
    provider = OllamaProvider(model_name="llama3.2")
    with patch(
        "httpx.AsyncClient.post",
        side_effect=httpx.ConnectTimeout("Connection timed out"),
    ):
        with pytest.raises(AIProviderTimeout):
            await provider.generate_response("Hello")


@pytest.mark.asyncio
async def test_ollama_read_timeout_raises_provider_timeout():
    provider = OllamaProvider(model_name="llama3.2")
    with patch(
        "httpx.AsyncClient.post", side_effect=httpx.ReadTimeout("Read timed out")
    ):
        with pytest.raises(AIProviderTimeout):
            await provider.generate_response("Hello")


@pytest.mark.asyncio
async def test_openai_stream_read_timeout_raises_provider_timeout():
    provider = OpenAIProvider(model_name="gpt-4o-mini")
    with patch(
        "httpx.AsyncClient.stream",
        side_effect=httpx.ReadTimeout("Stream read timed out"),
    ):
        with pytest.raises(AIProviderTimeout):
            async for _ in provider.generate_stream("Hello"):
                pass


@pytest.mark.asyncio
async def test_stream_cancellation_propagates_cleanly():
    provider = OllamaProvider(model_name="llama3.2")

    async def mock_stream_cancel(*args, **kwargs):
        raise asyncio.CancelledError
        yield

    with patch.object(provider, "generate_stream", mock_stream_cancel):
        gen = provider.generate_stream("Hello")
        with pytest.raises(asyncio.CancelledError):
            await gen.__anext__()


def test_client_disconnect_during_stream_does_not_persist_ai_message(
    client, user_and_chat
):
    user, chat = user_and_chat

    async def mock_stream_with_disconnect(*args, **kwargs):
        yield "First token "
        raise asyncio.CancelledError

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_stream_with_disconnect

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Test disconnect"},
            headers=auth_headers(user),
        )

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 0


def test_provider_timeout_in_chat_stream_yields_safe_error_and_no_ai_persistence(
    client, user_and_chat
):
    user, chat = user_and_chat

    async def mock_timeout_stream(*args, **kwargs):
        yield "Starting... "
        raise AIProviderTimeout()

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_timeout_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Test timeout"},
            headers=auth_headers(user),
        )

    assert response.status_code == 200

    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _ in events]

    assert event_names[0] == "stream_started"
    assert "sources" in event_names
    assert "chunk" in event_names
    assert event_names[-1] == "stream_error"

    error_events = [data for event_name, data in events if event_name == "stream_error"]
    assert error_events == [
        {
            "code": "provider_timeout",
            "message": "The AI provider timed out. Please try again.",
        }
    ]

    history = ChatRepository.get_history(
        chat_id=chat.id,
        user_id=user.id,
    )
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 0


def test_provider_unavailable_yields_safe_error_and_no_ai_persistence(
    client, user_and_chat
):
    user, chat = user_and_chat

    async def mock_unavail_stream(*args, **kwargs):
        raise AIProviderUnavailable()
        yield "not emitted"

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_unavail_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Test unavailable"},
            headers=auth_headers(user),
        )

    assert response.status_code == 200

    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _ in events]

    assert event_names[0] == "stream_started"
    assert "sources" in event_names
    assert event_names[-1] == "stream_error"

    error_events = [data for event_name, data in events if event_name == "stream_error"]
    assert error_events == [
        {
            "code": "provider_unavailable",
            "message": "The AI provider is temporarily unavailable. Please try again.",
        }
    ]

    history = ChatRepository.get_history(
        chat_id=chat.id,
        user_id=user.id,
    )
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 0


def test_normal_completion_persists_exactly_once(client, user_and_chat):
    user, chat = user_and_chat

    async def mock_ok_stream(*args, **kwargs):
        yield "Complete "
        yield "answer."

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_ok_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Normal prompt"},
            headers=auth_headers(user),
        )

    assert response.status_code == 200

    events = parse_sse_events(response.text)
    event_names = [event_name for event_name, _ in events]

    assert event_names[0] == "stream_started"
    assert "sources" in event_names

    chunk_events = [data for event_name, data in events if event_name == "chunk"]
    assert "".join(event["text"] for event in chunk_events) == "Complete answer."
    assert event_names[-1] == "stream_completed"

    completed_events = [
        data for event_name, data in events if event_name == "stream_completed"
    ]
    assert len(completed_events) == 1
    assert completed_events[0]["message_id"] is not None

    history = ChatRepository.get_history(
        chat_id=chat.id,
        user_id=user.id,
    )
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 1
    assert ai_messages[0].content == "Complete answer."


def test_stream_emits_structured_sources_event(client, user_and_chat, db_session):
    user, chat = user_and_chat

    async def mock_ok_stream(*args, **kwargs):
        yield "Answer."

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_ok_stream

    context_chunks = [
        {
            "id": 101,
            "content": "Secret chunk content that must not be exposed.",
            "page_number": 4,
            "chunk_index": 7,
            "distance": 0.3142,
        }
    ]

    # Persist pdf_context to the actual test DB session
    chat.pdf_context = "Indexed File: test.pdf"
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ), patch(
        "app.api.chat.VectorRepository.search_similar_chunks",
        return_value=context_chunks,
    ), patch(
        "app.api.chat.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ):
        response = client.post(
            "/chat/stream",
            json={
                "chat_id": chat.id,
                "prompt": "What is this document about?",
            },
            headers=auth_headers(user),
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse_events(response.text)
    source_events = [data for event_name, data in events if event_name == "sources"]

    assert len(source_events) == 1
    assert source_events[0] == {
        "sources": [
            {
                "id": 101,
                "page_number": 4,
                "chunk_index": 7,
                "distance": 0.3142,
            }
        ]
    }
    assert "Secret chunk content that must not be exposed." not in response.text
