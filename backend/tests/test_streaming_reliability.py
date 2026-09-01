from __future__ import annotations

import asyncio
import pytest

from app.services.ai_service import AIService
from app.services.providers.errors import (
    AIProviderResponseError,
    AIProviderTimeout,
    AIProviderUnavailable,
)


class FakeProvider:
    def __init__(self, tokens=None, error=None, delay: float = 0):
        self.tokens = tokens or []
        self.error = error
        self.delay = delay

    async def generate_stream(self, **kwargs):
        for token in self.tokens:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield token
        if self.error:
            raise self.error


@pytest.fixture
def service(monkeypatch):
    svc = AIService()
    monkeypatch.setattr(svc.rate_limiter, "allow", lambda user_id: True)
    return svc


async def collect(generator):
    return [item async for item in generator]


def configure_factory(monkeypatch, provider):
    monkeypatch.setattr(
        "app.services.ai_service.LLMProviderFactory.get_provider",
        lambda **kwargs: provider,
    )
    monkeypatch.setattr(
        "app.services.ai_service.LLMProviderFactory.validate_configuration",
        lambda **kwargs: (kwargs["provider"], kwargs["model"]),
    )


@pytest.mark.asyncio
async def test_successful_stream_emits_all_tokens(service, monkeypatch):
    provider = FakeProvider(tokens=["Hello", " ", "world"])
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="hello"))
    assert result == ["Hello", " ", "world"]


@pytest.mark.asyncio
async def test_successful_stream_completes_without_error(service, monkeypatch):
    provider = FakeProvider(tokens=["A", "B", "C"])
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert "".join(result) == "ABC"


@pytest.mark.asyncio
async def test_provider_failure_returns_safe_message(service, monkeypatch):
    provider = FakeProvider(tokens=["partial"], error=AIProviderUnavailable())
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert result[0] == "partial"
    assert "temporarily unavailable" in result[-1]
    assert "AIProviderUnavailable" not in "".join(result)


@pytest.mark.asyncio
async def test_provider_timeout_returns_safe_message(service, monkeypatch):
    provider = FakeProvider(error=AIProviderTimeout())
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert "timed out" in result[-1]
    assert "AIProviderTimeout" not in result[-1]


@pytest.mark.asyncio
async def test_provider_response_error_is_sanitized(service, monkeypatch):
    provider = FakeProvider(error=AIProviderResponseError("SECRET_PROVIDER_RESPONSE"))
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert "SECRET_PROVIDER_RESPONSE" not in "".join(result)


@pytest.mark.asyncio
async def test_malformed_provider_stream_is_safe(service, monkeypatch):
    provider = FakeProvider(tokens=["before"], error=AIProviderResponseError())
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert result[0] == "before"
    assert result[-1].startswith("\n[")


@pytest.mark.asyncio
async def test_client_cancellation_propagates(service, monkeypatch):
    class CancelProvider:
        async def generate_stream(self, **kwargs):
            raise asyncio.CancelledError
            yield

    provider = CancelProvider()
    configure_factory(monkeypatch, provider)

    generator = service.process_stream(user_id=1, prompt="test")
    with pytest.raises(asyncio.CancelledError):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_cancellation_does_not_become_provider_error(service, monkeypatch):
    class CancelProvider:
        async def generate_stream(self, **kwargs):
            raise asyncio.CancelledError
            yield

    provider = CancelProvider()
    configure_factory(monkeypatch, provider)

    generator = service.process_stream(user_id=1, prompt="test")
    with pytest.raises(asyncio.CancelledError):
        await generator.__anext__()


@pytest.mark.asyncio
async def test_concurrent_streams_do_not_share_state(service, monkeypatch):
    class DynamicProvider:
        def __init__(self):
            self.calls = 0

        async def generate_stream(self, **kwargs):
            self.calls += 1
            current = self.calls
            yield f"stream-{current}-a"
            await asyncio.sleep(0)
            yield f"stream-{current}-b"

    provider = DynamicProvider()
    configure_factory(monkeypatch, provider)

    first, second = await asyncio.gather(
        collect(service.process_stream(user_id=1, prompt="one")),
        collect(service.process_stream(user_id=2, prompt="two")),
    )
    assert first != second
    assert all(token for token in first)
    assert all(token for token in second)


@pytest.mark.asyncio
async def test_empty_provider_response_is_empty(service, monkeypatch):
    provider = FakeProvider(tokens=[])
    configure_factory(monkeypatch, provider)
    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert result == []


@pytest.mark.asyncio
async def test_rate_limited_stream_does_not_call_provider(service, monkeypatch):
    called = False

    class Provider:
        async def generate_stream(self, **kwargs):
            nonlocal called
            called = True
            yield "unexpected"

    provider = Provider()
    configure_factory(monkeypatch, provider)
    monkeypatch.setattr(service.rate_limiter, "allow", lambda user_id: False)

    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert called is False
    assert "Rate limit exceeded" in result[0]


@pytest.mark.asyncio
async def test_invalid_configuration_does_not_create_provider(service, monkeypatch):
    def invalid_configuration(**kwargs):
        raise ValueError("provider/model mismatch")

    called = False

    def get_provider(**kwargs):
        nonlocal called
        called = True
        return FakeProvider(["bad"])

    monkeypatch.setattr(
        "app.services.ai_service.LLMProviderFactory.validate_configuration",
        invalid_configuration,
    )
    monkeypatch.setattr(
        "app.services.ai_service.LLMProviderFactory.get_provider",
        get_provider,
    )

    result = await collect(service.process_stream(user_id=1, prompt="test"))
    assert called is False
    assert "Configuration Error" in result[0]
