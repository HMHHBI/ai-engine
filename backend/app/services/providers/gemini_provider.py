from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import AsyncGenerator, Dict, List, Optional

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.core.config import settings
from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.errors import (
    AIProviderConfigurationError,
    AIProviderResponseError,
    AIProviderTimeout,
    AIProviderUnavailable,
)

logger = logging.getLogger(__name__)

# The Gemini SDK is synchronous, so streaming requests require worker
# threads. Bound the number of active workers to prevent an unbounded
# accumulation of blocked SDK calls under cancellation or provider stalls.
_GEMINI_MAX_WORKERS = max(
    1,
    int(getattr(settings, "GEMINI_MAX_WORKERS", 4)),
)
_GEMINI_WORKER_SEMAPHORE = threading.BoundedSemaphore(
    _GEMINI_MAX_WORKERS,
)
_GEMINI_WORKER_TRACKER: set[threading.Thread] = set()
_GEMINI_WORKER_TRACKER_LOCK = threading.Lock()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        *,
        timeout: float | None = None,
        stream_max_seconds: float | None = None,
        idle_timeout: float | None = None,
    ) -> None:
        api_key = getattr(
            settings,
            "GEMINI_API_KEY",
            "",
        )

        self.client = genai.Client(api_key=api_key) if api_key else None

        self.model_name = model_name

        self.timeout = timeout if timeout is not None else settings.AI_REQUEST_TIMEOUT

        self.idle_timeout = (
            idle_timeout if idle_timeout is not None else settings.AI_READ_TIMEOUT
        )

        self.stream_max_seconds = (
            stream_max_seconds
            if stream_max_seconds is not None
            else settings.AI_STREAM_MAX_SECONDS
        )

    @staticmethod
    def _format_contents(
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        full_text = ""

        if system_prompt:
            full_text += f"System Instruction:\n" f"{system_prompt}\n\n"

        if history:
            for msg in history:
                role = msg.get(
                    "role",
                    "user",
                )
                text = msg.get(
                    "content",
                    msg.get("text", ""),
                )

                full_text += f"{role.capitalize()}: " f"{text}\n"

        full_text += f"User: {prompt}"

        return full_text

    def _require_client(self):
        if not self.client:
            raise AIProviderConfigurationError("Gemini provider is not configured.")

        return self.client

    @staticmethod
    def _register_worker(
        worker_thread: threading.Thread,
    ) -> None:
        with _GEMINI_WORKER_TRACKER_LOCK:
            _GEMINI_WORKER_TRACKER.add(worker_thread)

    @staticmethod
    def _unregister_worker(
        worker_thread: threading.Thread,
    ) -> None:
        with _GEMINI_WORKER_TRACKER_LOCK:
            _GEMINI_WORKER_TRACKER.discard(worker_thread)

    @staticmethod
    def active_worker_count() -> int:
        """Return the number of currently tracked Gemini workers."""
        with _GEMINI_WORKER_TRACKER_LOCK:
            return len(_GEMINI_WORKER_TRACKER)

    async def _acquire_worker_slot(self) -> None:
        """
        Acquire a bounded worker slot without blocking the event loop.

        Non-blocking semaphore attempts allow asyncio cancellation to
        interrupt acquisition immediately.
        """
        while True:
            acquired = _GEMINI_WORKER_SEMAPHORE.acquire(
                blocking=False,
            )

            if acquired:
                return

            await asyncio.sleep(0.01)

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        client = self._require_client()

        contents = self._format_contents(
            prompt,
            system_prompt,
            history,
        )

        timeout = kwargs.get(
            "timeout",
            self.timeout,
        )

        config = types.GenerateContentConfig(
            temperature=temperature,
        )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout,
            )

            text = getattr(
                result,
                "text",
                None,
            )

            if not text:
                raise AIProviderResponseError("Gemini returned an empty response.")

            return text

        except asyncio.TimeoutError as exc:
            logger.warning(
                "Gemini request timed out model=%s",
                self.model_name,
            )
            raise AIProviderTimeout() from exc

        except asyncio.CancelledError:
            logger.info(
                "Gemini request cancelled model=%s",
                self.model_name,
            )
            raise

        except APIError as exc:
            logger.warning(
                "Gemini API request failed model=%s",
                self.model_name,
            )
            raise AIProviderUnavailable() from exc

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        client = self._require_client()

        contents = self._format_contents(
            prompt,
            system_prompt,
            history,
        )

        idle_timeout = kwargs.get(
            "idle_timeout",
            self.idle_timeout,
        )

        max_stream_seconds = kwargs.get(
            "stream_max_seconds",
            self.stream_max_seconds,
        )

        queue_size = max(
            1,
            int(settings.GEMINI_QUEUE_SIZE),
        )
        queue_poll_seconds = max(
            0.01,
            float(settings.GEMINI_QUEUE_POLL_SECONDS),
        )
        worker_join_timeout = max(
            0.01,
            float(settings.GEMINI_WORKER_JOIN_TIMEOUT),
        )

        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be positive.")

        if max_stream_seconds <= 0:
            raise ValueError("stream_max_seconds must be positive.")

        item_queue: queue.Queue[object] = queue.Queue(
            maxsize=queue_size,
        )

        sentinel = object()
        stop_event = threading.Event()
        worker_done = threading.Event()
        worker_slot_acquired = False

        config = types.GenerateContentConfig(
            temperature=temperature,
        )

        worker_thread: threading.Thread | None = None

        def enqueue(
            item: object,
            *,
            allow_after_stop: bool = False,
        ) -> bool:
            """
            Put an item into the bounded queue with cancellation-aware
            backpressure.

            The worker never waits indefinitely for the async consumer.
            """
            while allow_after_stop or not stop_event.is_set():
                try:
                    item_queue.put(
                        item,
                        timeout=0.25,
                    )
                    return True
                except queue.Full:
                    continue

            return False

        def worker() -> None:
            nonlocal worker_thread

            current_thread = threading.current_thread()

            try:
                stream = client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )

                for chunk in stream:
                    if stop_event.is_set():
                        break

                    text = getattr(
                        chunk,
                        "text",
                        None,
                    )

                    if not text:
                        continue

                    if not enqueue(text):
                        break

            except APIError as exc:
                if not stop_event.is_set():
                    enqueue(exc)

            except TimeoutError as exc:
                if not stop_event.is_set():
                    enqueue(exc)

            except Exception as exc:
                if not stop_event.is_set():
                    enqueue(
                        AIProviderResponseError(
                            "Gemini returned an invalid or unusable response."
                        )
                    )
                    logger.exception(
                        "Unexpected Gemini streaming failure model=%s",
                        self.model_name,
                        exc_info=exc,
                    )

            finally:
                # A normal completion must notify the consumer. During
                # cancellation, the consumer is already terminating and
                # should not be kept alive merely to enqueue a sentinel.
                if not stop_event.is_set():
                    enqueue(sentinel)

                worker_done.set()

                self._unregister_worker(
                    current_thread,
                )

                if worker_slot_acquired:
                    _GEMINI_WORKER_SEMAPHORE.release()

        await self._acquire_worker_slot()
        worker_slot_acquired = True

        worker_thread = threading.Thread(
            target=worker,
            name="gemini-stream-worker",
            daemon=True,
        )

        self._register_worker(
            worker_thread,
        )

        worker_thread.start()

        deadline = time.monotonic() + max_stream_seconds
        last_activity = time.monotonic()

        try:
            while True:
                now = time.monotonic()
                remaining_total = deadline - now
                remaining_idle = idle_timeout - (now - last_activity)

                if remaining_total <= 0:
                    stop_event.set()
                    raise AIProviderTimeout(
                        "Gemini stream exceeded the maximum lifetime."
                    )

                if remaining_idle <= 0:
                    stop_event.set()
                    raise AIProviderTimeout(
                        "Gemini stream exceeded the provider idle timeout."
                    )

                wait_timeout = min(
                    queue_poll_seconds,
                    remaining_total,
                    remaining_idle,
                )

                try:
                    item = await asyncio.to_thread(
                        item_queue.get,
                        True,
                        wait_timeout,
                    )
                except queue.Empty:
                    # This is only the internal polling heartbeat.
                    # It is deliberately NOT a provider timeout.
                    continue

                if item is sentinel:
                    return

                last_activity = time.monotonic()

                if isinstance(
                    item,
                    AIProviderTimeout,
                ):
                    raise item

                if isinstance(
                    item,
                    APIError,
                ):
                    raise AIProviderUnavailable() from item

                if isinstance(
                    item,
                    TimeoutError,
                ):
                    raise AIProviderTimeout() from item

                if isinstance(
                    item,
                    AIProviderResponseError,
                ):
                    raise item

                if isinstance(
                    item,
                    BaseException,
                ):
                    raise AIProviderUnavailable() from item

                yield str(item)

        except asyncio.CancelledError:
            stop_event.set()

            logger.info(
                "Gemini stream cancelled model=%s",
                self.model_name,
            )

            raise

        finally:
            stop_event.set()

            if worker_thread is not None and not worker_done.is_set():
                try:
                    await asyncio.to_thread(
                        worker_done.wait,
                        worker_join_timeout,
                    )
                except asyncio.CancelledError:
                    # Preserve cancellation while still signalling the
                    # worker to terminate cooperatively.
                    raise

            if worker_thread is not None and worker_thread.is_alive():
                logger.warning(
                    "Gemini worker did not terminate within "
                    "cleanup timeout model=%s",
                    self.model_name,
                )
