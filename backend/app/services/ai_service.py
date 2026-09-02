from __future__ import annotations

import asyncio
import logging
import random
from typing import AsyncGenerator

from app.core.config import AIModel, AIProvider
from app.services.cache.memory_cache import MemoryCache
from app.services.providers.errors import (
    AIProviderConfigurationError,
    AIProviderError,
    AIProviderTimeout,
    AIProviderUnavailable,
)
from app.services.providers.factory import LLMProviderFactory
from app.services.rate_limit.memory_rate_limiter import MemoryRateLimiter

logger = logging.getLogger(__name__)


class AIService:
    """
    Application service responsible for LLM execution.

    Provider and model are explicit inputs and are validated together
    by LLMProviderFactory before a provider is instantiated.
    """

    def __init__(self):
        self.cache = MemoryCache()
        self.rate_limiter = MemoryRateLimiter()

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _normalize_provider(
        provider: AIProvider | str,
    ) -> AIProvider:
        if isinstance(provider, AIProvider):
            return provider

        try:
            return AIProvider(str(provider).strip().lower())
        except ValueError as exc:
            valid = ", ".join(item.value for item in AIProvider)
            raise ValueError(
                f"Unsupported AI provider '{provider}'. Supported providers: {valid}."
            ) from exc

    @staticmethod
    def _normalize_model(
        model: AIModel | str,
    ) -> AIModel:
        if isinstance(model, AIModel):
            return model

        try:
            return AIModel(str(model).strip())
        except ValueError as exc:
            valid = ", ".join(item.value for item in AIModel)
            raise ValueError(
                f"Unsupported AI model '{model}'. Supported models: {valid}."
            ) from exc

    @staticmethod
    def _fallback() -> str:
        return random.choice(
            [
                "AI is currently busy. Please try again shortly.",
                "Temporary system delay. Please retry your request.",
                "Unable to complete the request right now. Please retry.",
            ]
        )

    # ============================================================
    # Stream
    # ============================================================

    async def process_stream(
        self,
        user_id: int,
        prompt: str,
        chat_history: list[dict[str, str]] | None = None,
        rag_context: str | None = None,
        task: str = "general",
        provider: AIProvider | str = AIProvider.OLLAMA,
        model: AIModel | str = AIModel.OLLAMA_LLAMA_3_2,
    ) -> AsyncGenerator[str, None]:
        clean_prompt = prompt.strip()

        if not clean_prompt:
            yield "Please provide a message."
            return

        try:
            normalized_provider = self._normalize_provider(provider)
            normalized_model = self._normalize_model(model)

            normalized_provider, normalized_model = (
                LLMProviderFactory.validate_configuration(
                    provider=normalized_provider,
                    model=normalized_model,
                )
            )
        except ValueError:
            logger.warning(
                "Invalid AI configuration provider=%s model=%s",
                provider,
                model,
            )
            yield "[Configuration Error: invalid AI configuration.]"
            return

        if not self.rate_limiter.allow(user_id):
            yield "Rate limit exceeded. Please wait a moment before sending more messages."
            return

        system_instructions = {
            "email": (
                "You are a professional email writer. "
                "Write clear, concise, professional emails."
            ),
            "blog": (
                "You are an expert technical blog writer. "
                "Produce accurate, well-structured technical content."
            ),
            "code": (
                "You are a senior full-stack software engineer. "
                "Provide production-quality technical solutions."
            ),
            "general": "You are a helpful and intelligent AI assistant.",
        }

        base_instruction = system_instructions.get(
            task,
            system_instructions["general"],
        )

        system_prompt = base_instruction

        if rag_context:
            system_prompt += (
                "\n\n"
                "DOCUMENT GROUNDING RULES:\n"
                "1. Answer document-specific questions only from the provided document context.\n"
                "2. Do not invent facts not supported by the context.\n"
                "3. Do not use general knowledge to fill missing document information.\n"
                "4. If the context is insufficient, explicitly say so instead of guessing.\n\n"
                "[DOCUMENT CONTEXT]\n"
                f"{rag_context}"
            )

        try:
            llm_provider = LLMProviderFactory.get_provider(
                provider=normalized_provider,
                model=normalized_model,
            )
        except ValueError:
            logger.warning(
                "Provider creation failed provider=%s model=%s",
                normalized_provider.value,
                normalized_model.value,
            )
            yield "[Configuration Error: invalid AI configuration.]"
            return

        logger.info(
            "AI stream started user_id=%s provider=%s model=%s task=%s",
            user_id,
            normalized_provider.value,
            normalized_model.value,
            task,
        )

        try:
            async for chunk in llm_provider.generate_stream(
                prompt=clean_prompt,
                system_prompt=system_prompt,
                history=chat_history,
                temperature=0.2,
            ):
                if chunk:
                    yield chunk

        except asyncio.CancelledError:
            logger.info(
                "AI stream cancelled user_id=%s provider=%s model=%s",
                user_id,
                normalized_provider.value,
                normalized_model.value,
            )
            raise

        except AIProviderTimeout:
            logger.warning(
                "AI provider timeout user_id=%s provider=%s model=%s",
                user_id,
                normalized_provider.value,
                normalized_model.value,
            )
            yield "\n[The AI provider timed out. Please try again.]"

        except AIProviderUnavailable:
            logger.warning(
                "AI provider unavailable user_id=%s provider=%s model=%s",
                user_id,
                normalized_provider.value,
                normalized_model.value,
            )
            yield "\n[The AI provider is temporarily unavailable. Please try again.]"

        except AIProviderConfigurationError:
            logger.error(
                "AI provider configuration failure provider=%s model=%s",
                normalized_provider.value,
                normalized_model.value,
            )
            yield "\n[The AI provider is not configured correctly.]"

        except AIProviderError:
            logger.exception(
                "AI provider error user_id=%s provider=%s model=%s",
                user_id,
                normalized_provider.value,
                normalized_model.value,
            )
            yield "\n[The AI provider could not complete the request.]"

        except Exception:
            logger.exception(
                "AIService stream failed user_id=%s provider=%s model=%s",
                user_id,
                normalized_provider.value,
                normalized_model.value,
            )
            yield f"\n[System Error: {self._fallback()}]"

    # ============================================================
    # Chat Title
    # ============================================================

    async def generate_chat_title(
        self,
        prompt: str,
        provider: AIProvider | str = AIProvider.OLLAMA,
        model: AIModel | str = AIModel.OLLAMA_LLAMA_3_2,
    ) -> str:
        clean_prompt = prompt.strip()

        if not clean_prompt:
            return "New Chat"

        try:
            normalized_provider = self._normalize_provider(provider)
            normalized_model = self._normalize_model(model)

            normalized_provider, normalized_model = (
                LLMProviderFactory.validate_configuration(
                    provider=normalized_provider,
                    model=normalized_model,
                )
            )

            llm_provider = LLMProviderFactory.get_provider(
                provider=normalized_provider,
                model=normalized_model,
            )

            response = await llm_provider.generate_response(
                prompt=(
                    "Generate a concise 3-4 word title for this "
                    "conversation. Return ONLY the title text.\n\n"
                    f"Conversation:\n{clean_prompt}"
                ),
                temperature=0.3,
            )

            if not response:
                return clean_prompt[:25]

            title = response.strip().replace('"', "").replace("'", "")
            return title[:80]

        except Exception:
            logger.exception(
                "Failed to generate chat title provider=%s model=%s",
                provider,
                model,
            )
            return clean_prompt[:25]
