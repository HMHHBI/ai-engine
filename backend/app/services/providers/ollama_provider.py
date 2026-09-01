from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.errors import (
    AIProviderResponseError,
    AIProviderTimeout,
    AIProviderUnavailable,
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    def __init__(
        self,
        model_name: str = "llama3.2",
        *,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = getattr(
            settings,
            "OLLAMA_BASE_URL",
            "http://host.docker.internal:11434",
        ).rstrip("/")
        self.model = model_name
        self.timeout = timeout

    @staticmethod
    def _build_messages(
        prompt: str,
        system_prompt: Optional[str],
        history: Optional[List[Dict[str, str]]],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        if history:
            messages.extend(history)

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        return messages

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        messages = self._build_messages(
            prompt,
            system_prompt,
            history,
        )

        try:
            timeout = kwargs.get(
                "timeout",
                self.timeout,
            )

            async with httpx.AsyncClient(
                timeout=timeout,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                        },
                    },
                )

                response.raise_for_status()

                data = response.json()

                content = data.get(
                    "message",
                    {},
                ).get(
                    "content",
                    "",
                )

                if not isinstance(content, str):
                    raise AIProviderResponseError(
                        "Ollama returned an invalid response."
                    )

                return content

        except httpx.TimeoutException as exc:
            logger.warning(
                "Ollama request timed out model=%s",
                self.model,
            )
            raise AIProviderTimeout() from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Ollama returned HTTP error status=%s model=%s",
                exc.response.status_code,
                self.model,
            )
            raise AIProviderUnavailable() from exc

        except httpx.RequestError as exc:
            logger.warning(
                "Ollama network request failed model=%s",
                self.model,
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
        messages = self._build_messages(
            prompt,
            system_prompt,
            history,
        )

        timeout = kwargs.get(
            "timeout",
            self.timeout,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                        "options": {
                            "temperature": temperature,
                        },
                    },
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise AIProviderResponseError(
                                "Ollama returned malformed stream data."
                            ) from exc

                        content = data.get("message", {}).get("content", "")

                        if content:
                            yield content

        except asyncio.CancelledError:
            logger.info(
                "Ollama stream cancelled model=%s",
                self.model,
            )
            raise

        except httpx.TimeoutException as exc:
            logger.warning(
                "Ollama stream timed out model=%s",
                self.model,
            )
            raise AIProviderTimeout() from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Ollama stream HTTP error status=%s model=%s",
                exc.response.status_code,
                self.model,
            )
            raise AIProviderUnavailable() from exc

        except httpx.RequestError as exc:
            logger.warning(
                "Ollama stream network failure model=%s",
                self.model,
            )
            raise AIProviderUnavailable() from exc
