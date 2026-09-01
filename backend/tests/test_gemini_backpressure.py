from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.errors import AIProviderTimeout


class FakeGeminiStream:
    def __init__(
        self,
        count: int,
    ):
        self.count = count

    def __iter__(self):
        for index in range(self.count):
            yield SimpleNamespace(
                text=f"token-{index}",
            )


@pytest.mark.asyncio
async def test_gemini_stream_handles_more_than_queue_capacity():
    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        timeout=5.0,
        stream_max_seconds=5.0,
    )

    fake_client = MagicMock()
    fake_client.models.generate_content_stream.return_value = FakeGeminiStream(100)
    provider.client = fake_client

    tokens = []
    async for token in provider.generate_stream(
        prompt="stress test",
    ):
        tokens.append(token)
        await asyncio.sleep(0.001)

    assert len(tokens) == 100
    assert tokens[0] == "token-0"
    assert tokens[-1] == "token-99"


@pytest.mark.asyncio
async def test_gemini_cancellation_stops_worker():
    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        timeout=30.0,
        stream_max_seconds=30.0,
    )

    class SlowBlockingStream:
        def __iter__(self):
            yield SimpleNamespace(text="token-1")
            # Hold production to ensure consumer awaits signal
            time.sleep(1.0)
            yield SimpleNamespace(text="token-2")

    fake_client = MagicMock()
    fake_client.models.generate_content_stream.return_value = SlowBlockingStream()
    provider.client = fake_client

    stream = provider.generate_stream(prompt="cancel test")

    first_token = await anext(stream)
    assert first_token == "token-1"

    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    await stream.aclose()


@pytest.mark.asyncio
async def test_gemini_stream_timeout_is_typed_error():
    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        timeout=0.05,
        stream_max_seconds=0.05,
    )

    class SlowStream:
        def __iter__(self):
            time.sleep(0.2)
            yield SimpleNamespace(
                text="late",
            )

    fake_client = MagicMock()
    fake_client.models.generate_content_stream.return_value = SlowStream()
    provider.client = fake_client

    stream = provider.generate_stream(
        prompt="timeout test",
    )

    with pytest.raises(AIProviderTimeout):
        await stream.__anext__()

    await stream.aclose()
