import json
import httpx
from typing import AsyncGenerator, Dict, List, Optional
from app.core.config import settings
from app.services.providers.base_provider import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """Concrete LLM Provider for OpenAI API (and OpenAI-compatible APIs like Groq/DeepSeek)."""

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.base_url = getattr(
            settings, "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        self.model_name = model_name

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        messages = self._build_messages(prompt, system_prompt, history)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        messages = self._build_messages(prompt, system_prompt, history)
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and not line.endswith("[DONE]"):
                        raw_data = line.replace("data: ", "").strip()
                        if raw_data:
                            data = json.loads(raw_data)
                            delta = data["choices"][0].get("delta", {})
                            token = delta.get("content", "")
                            if token:
                                yield token