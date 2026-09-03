import asyncio
import json
import logging
import time
from unittest.mock import patch
import pytest

from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.factory import LLMProviderFactory


class MockLogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def log_capture():
    handler = MockLogCaptureHandler()
    logger = logging.getLogger("app.api.chat")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)


@pytest.fixture
def user_and_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Telemetry User",
        email=f"telemetry_{ts}@example.com",
        password="securepassword123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


class MockTelemetryProvider(BaseLLMProvider):
    async def generate_response(
        self, prompt: str, system_prompt: str | None = None
    ) -> str:
        return "mock response"

    async def generate_stream(self, prompt: str, system_prompt: str | None = None):
        await asyncio.sleep(0.01)
        yield ""  # Empty chunk to test chunk counter filter
        yield "Hello"
        yield " world"


def test_successful_stream_emits_telemetry(client, user_and_chat, log_capture):
    user, chat = user_and_chat

    with patch.object(
        LLMProviderFactory, "get_provider", return_value=MockTelemetryProvider()
    ):
        headers = auth_headers(user)
        headers["X-Correlation-ID"] = "test-corr-telemetry"

        response = client.post(
            "/chat/stream",
            json={
                "chat_id": chat.id,
                "prompt": "Test telemetry prompt",
                "model": "gemini-2.5-flash",
            },
            headers=headers,
        )
        assert response.status_code == 200
        _ = response.text  # Consume stream to execute event_generator

    events = [getattr(r, "event", None) for r in log_capture.records]

    assert "chat_request_started" in events
    assert "ai_provider_selected" in events
    assert "ai_stream_started" in events
    assert "ai_first_token" in events
    assert "ai_stream_completed" in events
    assert "chat_request_completed" in events

    completed_rec = next(
        r
        for r in log_capture.records
        if getattr(r, "event", None) == "ai_stream_completed"
    )
    assert completed_rec.chunk_count == 2
    assert completed_rec.duration_ms >= 0

    first_token_rec = next(
        r for r in log_capture.records if getattr(r, "event", None) == "ai_first_token"
    )
    assert first_token_rec.time_to_first_token_ms >= 0


def test_telemetry_never_logs_sensitive_payloads(client, user_and_chat, log_capture):
    user, chat = user_and_chat
    secret_prompt = "TOP_SECRET_PROMPT_12345"

    with patch.object(
        LLMProviderFactory, "get_provider", return_value=MockTelemetryProvider()
    ):
        headers = auth_headers(user)

        response = client.post(
            "/chat/stream",
            json={
                "chat_id": chat.id,
                "prompt": secret_prompt,
                "model": "gemini-2.5-flash",
            },
            headers=headers,
        )
        assert response.status_code == 200
        _ = response.text

    for record in log_capture.records:
        record_str = json.dumps(record.__dict__, default=str)
        assert secret_prompt not in record_str
