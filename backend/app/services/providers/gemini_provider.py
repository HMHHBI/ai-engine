from __future__ import annotations

import asyncio
import logging
import threading
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
        timeout: float = 120.0,
    ) -> None:
        api_key = getattr(
            settings,
            "GEMINI_API_KEY",
            "",
        )

        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model_name = model_name
        self.timeout = timeout

    @staticmethod
    def _format_contents(
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        full_text = ""

        if system_prompt:
            full_text += f"System Instruction:\n{system_prompt}\n\n"

        if history:
            for msg in history:
                role = msg.get("role", "user")
                text = msg.get("content", msg.get("text", ""))
                full_text += f"{role.capitalize()}: {text}\n"

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
        contents = self._format_contents(prompt, system_prompt, history)
        timeout = kwargs.get("timeout", self.timeout)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model_name,
                    contents=contents,
                ),
                timeout=timeout,
            )

            text = getattr(result, "text", None)
            if not text:
                raise AIProviderResponseError("Gemini returned an empty response.")
            return text

        except asyncio.TimeoutError as exc:
            logger.warning("Gemini request timed out model=%s", self.model_name)
            raise AIProviderTimeout() from exc
        except asyncio.CancelledError:
            logger.info("Gemini request cancelled model=%s", self.model_name)
            raise
        except APIError as exc:
            logger.warning("Gemini API request failed model=%s", self.model_name)
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
        contents = self._format_contents(prompt, system_prompt, history)
        timeout = kwargs.get("timeout", self.timeout)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        sentinel = object()
        stop_event = threading.Event()

        def worker() -> None:
            try:
                stream = client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                )

                for chunk in stream:
                    if stop_event.is_set():
                        break

                    text = getattr(chunk, "text", None)
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)

            except BaseException as exc:
                if not stop_event.is_set():
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        worker_thread = threading.Thread(target=worker, daemon=True)
        worker_thread.start()

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=timeout)
                except asyncio.TimeoutError as exc:
                    stop_event.set()
                    raise AIProviderTimeout() from exc

                if item is sentinel:
                    break

                if isinstance(item, asyncio.CancelledError):
                    raise item

                if isinstance(item, (APIError, BaseException)):
                    raise AIProviderUnavailable() from item

                yield str(item)

        except asyncio.CancelledError:
            stop_event.set()
            logger.info("Gemini stream cancelled model=%s", self.model_name)
            raise
        finally:
            stop_event.set()
