from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from app.core.config import settings
from app.services.providers.errors import AIProviderTimeout
from app.services.providers.gemini_provider import (
    GeminiProvider,
    _GEMINI_WORKER_TRACKER,
    _GEMINI_WORKER_TRACKER_LOCK,
)


class FakeGeminiStream:
    def __init__(
        self,
        chunks: list[str],
        delays: list[float] | None = None,
    ) -> None:
        self.chunks = chunks
        self.delays = delays or [0.0] * len(chunks)

    def __iter__(self):
        for chunk, delay in zip(
            self.chunks,
            self.delays,
        ):
            if delay:
                time.sleep(delay)

            yield SimpleNamespace(
                text=chunk,
            )


def make_provider(
    fake_stream,
    *,
    idle_timeout: float = 1.0,
    max_stream_seconds: float = 3.0,
    queue_poll_seconds: float = 0.05,
) -> GeminiProvider:
    client = MagicMock()
    client.models.generate_content_stream.return_value = fake_stream

    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        idle_timeout=idle_timeout,
        stream_max_seconds=max_stream_seconds,
    )
    provider.client = client

    return provider


def active_worker_count() -> int:
    with _GEMINI_WORKER_TRACKER_LOCK:
        return len(_GEMINI_WORKER_TRACKER)


@pytest.fixture(autouse=True)
def patch_gemini_poll_interval(monkeypatch):
    monkeypatch.setattr(
        settings,
        "GEMINI_QUEUE_POLL_SECONDS",
        0.05,
    )


@pytest.mark.asyncio
async def test_slow_chunk_cadence_does_not_trigger_false_timeout():
    """
    A 500 ms inter-chunk delay is greater than the internal queue polling
    interval but below the provider idle timeout, so the stream must
    continue normally.
    """
    stream = FakeGeminiStream(
        chunks=[
            "first ",
            "second ",
            "third",
        ],
        delays=[
            0.0,
            0.5,
            0.5,
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=1.0,
        max_stream_seconds=3.0,
    )

    received: list[str] = []

    async for token in provider.generate_stream(
        "hello",
        temperature=0.4,
    ):
        received.append(token)

    assert received == [
        "first ",
        "second ",
        "third",
    ]


@pytest.mark.asyncio
async def test_queue_poll_is_not_provider_timeout():
    """
    The queue polling heartbeat may expire repeatedly while waiting for
    a provider chunk. Those polling expirations must never become
    AIProviderTimeout exceptions by themselves.
    """
    stream = FakeGeminiStream(
        chunks=[
            "first",
            "second",
        ],
        delays=[
            0.0,
            0.35,
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=1.0,
        max_stream_seconds=3.0,
    )

    received: list[str] = []

    async for token in provider.generate_stream("hello"):
        received.append(token)

    assert received == [
        "first",
        "second",
    ]


@pytest.mark.asyncio
async def test_genuine_idle_timeout_triggers():
    """
    No provider chunk arrives before the configured idle timeout.
    """
    stream = FakeGeminiStream(
        chunks=[
            "first",
            "second",
        ],
        delays=[
            0.0,
            1.0,
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=0.2,
        max_stream_seconds=3.0,
    )

    received: list[str] = []

    with pytest.raises(AIProviderTimeout) as exc_info:
        async for token in provider.generate_stream("hello"):
            received.append(token)

    assert "idle timeout" in str(exc_info.value).lower()
    assert received == ["first"]


@pytest.mark.asyncio
async def test_absolute_stream_lifetime_exhaustion():
    """
    Continuous provider activity must not allow a stream to exceed its
    absolute lifetime.
    """
    stream = FakeGeminiStream(
        chunks=[
            "one",
            "two",
            "three",
            "four",
        ],
        delays=[
            0.0,
            0.15,
            0.15,
            0.15,
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=1.0,
        max_stream_seconds=0.25,
    )

    received: list[str] = []

    with pytest.raises(AIProviderTimeout) as exc_info:
        async for token in provider.generate_stream("hello"):
            received.append(token)

    assert "maximum lifetime" in str(exc_info.value).lower()
    assert received


@pytest.mark.asyncio
async def test_worker_is_cleaned_after_normal_completion():
    stream = FakeGeminiStream(
        chunks=[
            "complete",
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=1.0,
        max_stream_seconds=2.0,
    )

    before = active_worker_count()

    received = [token async for token in provider.generate_stream("hello")]

    await asyncio.sleep(0.05)

    after = active_worker_count()

    assert received == ["complete"]
    assert after == before


@pytest.mark.asyncio
async def test_worker_is_cleaned_after_idle_timeout():
    stream = FakeGeminiStream(
        chunks=[
            "first",
            "second",
        ],
        delays=[
            0.0,
            0.5,
        ],
    )

    provider = make_provider(
        stream,
        idle_timeout=0.1,
        max_stream_seconds=2.0,
    )

    before = active_worker_count()

    with pytest.raises(AIProviderTimeout):
        async for _ in provider.generate_stream("hello"):
            pass

    await asyncio.sleep(0.1)

    after = active_worker_count()

    assert after == before


@pytest.mark.asyncio
async def test_worker_is_signalled_on_consumer_cancellation():
    stream_started = threading.Event()
    worker_finished = threading.Event()

    class BlockingStream:
        def __iter__(self):
            stream_started.set()

            while not worker_finished.is_set():
                time.sleep(0.01)

            return
            yield

    stream = BlockingStream()

    provider = make_provider(
        stream,
        idle_timeout=10.0,
        max_stream_seconds=20.0,
    )

    generator = provider.generate_stream("hello")

    task = asyncio.create_task(generator.__anext__())

    await asyncio.to_thread(
        stream_started.wait,
        1.0,
    )

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    worker_finished.set()

    await asyncio.sleep(0.2)

    assert active_worker_count() == 0


@pytest.mark.asyncio
async def test_worker_concurrency_is_bounded(monkeypatch):
    """
    The provider must never have more active Gemini worker threads than
    the configured module-level worker bound.
    """
    monkeypatch.setattr(
        "app.services.providers.gemini_provider._GEMINI_MAX_WORKERS",
        2,
    )

    provider_module = __import__(
        "app.services.providers.gemini_provider",
        fromlist=["_GEMINI_WORKER_SEMAPHORE"],
    )

    # Replacing the semaphore here makes the test deterministic without
    # mutating the production worker bound permanently.
    original_semaphore = provider_module._GEMINI_WORKER_SEMAPHORE
    provider_module._GEMINI_WORKER_SEMAPHORE = threading.BoundedSemaphore(2)

    release_workers = threading.Event()
    started_workers = 0
    started_lock = threading.Lock()
    max_seen_workers = 0

    class BlockingStream:
        def __iter__(self):
            nonlocal started_workers, max_seen_workers

            with started_lock:
                started_workers += 1
                max_seen_workers = max(
                    max_seen_workers,
                    started_workers,
                )

            while not release_workers.is_set():
                time.sleep(0.01)

            with started_lock:
                started_workers -= 1

            yield SimpleNamespace(text="done")

    try:
        providers = [
            make_provider(
                BlockingStream(),
                idle_timeout=5.0,
                max_stream_seconds=10.0,
            )
            for _ in range(4)
        ]

        tasks = [
            asyncio.create_task(providers[index].generate_stream("hello").__anext__())
            for index in range(4)
        ]

        await asyncio.sleep(0.2)

        with started_lock:
            assert max_seen_workers <= 2

        release_workers.set()

        for task in tasks:
            try:
                await task
            except (StopAsyncIteration, AIProviderTimeout):
                pass

    finally:
        release_workers.set()
        provider_module._GEMINI_WORKER_SEMAPHORE = original_semaphore


@pytest.mark.asyncio
async def test_temperature_is_passed_to_generate_content_config():
    stream = FakeGeminiStream(
        chunks=["response"],
    )

    provider = make_provider(
        stream,
    )

    async for _ in provider.generate_stream(
        "hello",
        temperature=0.73,
    ):
        pass

    config = provider.client.models.generate_content_stream.call_args.kwargs["config"]

    assert config.temperature == 0.73
