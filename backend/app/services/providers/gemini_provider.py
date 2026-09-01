from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import AsyncGenerator, Dict, List, Optional

from google import genai
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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        *,
        timeout: float | None = None,
        stream_max_seconds: float | None = None,
    ) -> None:
        api_key = getattr(
            settings,
            "GEMINI_API_KEY",
            "",
        )

        self.client = genai.Client(api_key=api_key) if api_key else None

        self.model_name = model_name

        self.timeout = timeout if timeout is not None else settings.AI_REQUEST_TIMEOUT

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

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
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

        timeout = kwargs.get(
            "timeout",
            self.timeout,
        )

        max_stream_seconds = kwargs.get(
            "stream_max_seconds",
            self.stream_max_seconds,
        )

        queue_size = settings.GEMINI_QUEUE_SIZE
        queue_poll_seconds = settings.GEMINI_QUEUE_POLL_SECONDS
        worker_join_timeout = settings.GEMINI_WORKER_JOIN_TIMEOUT

        item_queue: queue.Queue[object] = queue.Queue(
            maxsize=queue_size,
        )

        sentinel = object()
        stop_event = threading.Event()
        worker_done = threading.Event()

        loop = asyncio.get_running_loop()
        queue_signal = asyncio.Event()

        def signal_consumer() -> None:
            if not loop.is_closed():
                queue_signal.set()

        def enqueue(item: object) -> bool:
            """
            Put an item into the bounded queue with cancellation-aware
            backpressure.

            The worker never waits indefinitely for the async consumer.
            """
            while not stop_event.is_set():
                try:
                    item_queue.put(
                        item,
                        timeout=0.25,
                    )
                    loop.call_soon_threadsafe(
                        signal_consumer,
                    )
                    return True
                except queue.Full:
                    continue

            return False

        def worker() -> None:
            try:
                stream = client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
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

            except BaseException as exc:
                if not stop_event.is_set():
                    enqueue(exc)

            finally:
                enqueue(sentinel)
                worker_done.set()

                try:
                    loop.call_soon_threadsafe(
                        signal_consumer,
                    )
                except RuntimeError:
                    pass

        worker_thread = threading.Thread(
            target=worker,
            name="gemini-stream-worker",
            daemon=True,
        )

        worker_thread.start()

        deadline = time.monotonic() + max_stream_seconds

        try:
            while True:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    stop_event.set()
                    raise AIProviderTimeout()

                if item_queue.empty():
                    queue_signal.clear()

                    try:
                        await asyncio.wait_for(
                            queue_signal.wait(),
                            timeout=min(
                                remaining,
                                timeout,
                                queue_poll_seconds,
                            ),
                        )
                    except asyncio.TimeoutError as exc:
                        stop_event.set()

                        if time.monotonic() >= deadline:
                            raise AIProviderTimeout() from exc

                        raise AIProviderTimeout() from exc

                while True:
                    try:
                        item = item_queue.get_nowait()
                    except queue.Empty:
                        break

                    if item is sentinel:
                        return

                    if isinstance(
                        item,
                        BaseException,
                    ):
                        if isinstance(
                            item,
                            asyncio.CancelledError,
                        ):
                            raise item

                        if isinstance(
                            item,
                            APIError,
                        ):
                            raise AIProviderUnavailable() from item

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

            if not worker_done.is_set():
                await asyncio.to_thread(
                    worker_done.wait,
                    worker_join_timeout,
                )

            if worker_thread.is_alive():
                logger.warning(
                    "Gemini worker did not terminate within "
                    "cleanup timeout model=%s",
                    self.model_name,
                )
