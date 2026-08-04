import asyncio
from typing import AsyncGenerator, Dict, List, Optional
from google import genai
from google.genai.errors import APIError

from app.core.config import settings
from app.services.providers.base_provider import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Concrete LLM Provider for Google Gemini using official google-genai SDK."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=api_key) if api_key else None
        self.model_name = model_name

    def _format_contents(
        self,
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

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        if not self.client:
            return "Error: GEMINI_API_KEY is not configured in environment settings."

        contents = self._format_contents(prompt, system_prompt, history)

        try:
            res = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents,
            )
            if res.text:
                return res.text
        except APIError as e:
            print(f"❌ Gemini API Error: {e}")
            return f"Gemini API Error: {str(e)}"
        except Exception as e:
            print(f"❌ Gemini Error: {e}")

        return "Gemini Service is currently unavailable."

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        if not self.client:
            yield "Error: GEMINI_API_KEY is not configured in environment settings."
            return

        contents = self._format_contents(prompt, system_prompt, history)

        try:
            response_stream = await asyncio.to_thread(
                self.client.models.generate_content_stream,
                model=self.model_name,
                contents=contents,
            )
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            print(f"❌ Gemini Streaming Error: {e}")
            yield f" [Gemini Stream Error: {str(e)}]"
