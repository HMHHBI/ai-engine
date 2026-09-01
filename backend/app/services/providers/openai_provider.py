from __future__ import annotations

import asyncio
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


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible streaming provider."""

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        *,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = getattr(
            settings,
            "OPENAI_API_KEY",
            "",
        )

        self.base_url = getattr(
            settings,
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ).rstrip("/")

        self.model_name = model_name
        self.timeout = timeout

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_messages(
        prompt: str,
        system_prompt: Optional[str],
        history: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []

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
                    f"{self.base_url}/chat/completions",
                    headers=self._build_headers(),
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": False,
                    },
                )

                response.raise_for_status()

                data = response.json()

                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    raise AIProviderResponseError(
                        "OpenAI returned an invalid response."
                    ) from exc

        except httpx.TimeoutException as exc:
            logger.warning(
                "OpenAI request timed out model=%s",
                self.model_name,
            )
            raise AIProviderTimeout() from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenAI request failed status=%s model=%s",
                exc.response.status_code,
                self.model_name,
            )
            raise AIProviderUnavailable() from exc

        except httpx.RequestError as exc:
            logger.warning(
                "OpenAI network request failed model=%s",
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
                    f"{self.base_url}/chat/completions",
                    headers=self._build_headers(),
                    json={
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue

                        raw_data = line[5:].strip()

                        if raw_data == "[DONE]":
                            return

                        if not raw_data:
                            continue

                        try:
                            data = json.loads(raw_data)
                        except json.JSONDecodeError as exc:
                            raise AIProviderResponseError(
                                "OpenAI returned malformed stream data."
                            ) from exc

                        try:
                            delta = data["choices"][0].get("delta", {})
                        except (KeyError, IndexError, TypeError) as exc:
                            raise AIProviderResponseError(
                                "OpenAI returned an invalid stream event."
                            ) from exc

                        token = delta.get(
                            "content",
                            "",
                        )

                        if token:
                            yield token

        except asyncio.CancelledError:
            logger.info(
                "OpenAI stream cancelled model=%s",
                self.model_name,
            )
            raise

        except httpx.TimeoutException as exc:
            logger.warning(
                "OpenAI stream timed out model=%s",
                self.model_name,
            )
            raise AIProviderTimeout() from exc

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "OpenAI stream failed status=%s model=%s",
                exc.response.status_code,
                self.model_name,
            )
            raise AIProviderUnavailable() from exc

        except httpx.RequestError as exc:
            logger.warning(
                "OpenAI stream network failure model=%s",
                self.model_name,
            )
            raise AIProviderUnavailable() from exc
