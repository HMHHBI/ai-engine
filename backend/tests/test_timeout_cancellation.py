from __future__ import annotations

import asyncio
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
        assert "[The AI provider timed out. Please try again.]" in response.text

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
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
        assert (
            "[The AI provider is temporarily unavailable. Please try again.]"
            in response.text
        )

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
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
        assert "Complete answer." in response.text

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 1
    assert ai_messages[0].content == "Complete answer."
