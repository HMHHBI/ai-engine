import random
from typing import AsyncGenerator, Dict, List, Optional
from app.services.cache.memory_cache import MemoryCache
from app.services.rate_limit.memory_rate_limiter import MemoryRateLimiter
from app.services.providers.factory import LLMProviderFactory, ModelProviderEnum


class AIService:
    def __init__(self):
        self.cache = MemoryCache()
        self.rate_limiter = MemoryRateLimiter()

    def _fallback(self) -> str:
        return random.choice(
            [
                "AI is currently busy. Please try again shortly.",
                "Temporary system delay. Retrying your request...",
                "Unable to complete request right now. Please retry.",
            ]
        )

    async def process_stream(
        self,
        user_id: int,
        prompt: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        rag_context: Optional[str] = None,
        task: str = "general",
        model_name: str = ModelProviderEnum.OLLAMA_LLAMA,
    ) -> AsyncGenerator[str, None]:
        """
        Unified Stream Handler using Factory Strategy Pattern & Vector RAG Context.
        """
        # 1. Rate Limiting Check
        if not self.rate_limiter.allow(user_id):
            yield "⚠️ Rate limit exceeded. Please wait a moment before sending more messages."
            return

        # 2. System Prompt Engineering & Context Assembly
        system_instructions = {
            "email": "You are a professional email writer.",
            "blog": "You are an expert technical blog writer.",
            "code": "You are a senior full-stack software engineer.",
            "general": "You are a helpful and intelligent AI assistant.",
        }
        base_instruction = system_instructions.get(task, system_instructions["general"])

        system_prompt = base_instruction
        if rag_context:
            system_prompt += (
                "\n\nCRITICAL CONTEXT INSTRUCTIONS:\n"
                "Answer the question using ONLY the provided [DOCUMENT CONTEXT] below. "
                "If the context does not contain the answer, politely decline to answer based on documents.\n\n"
                f"[DOCUMENT CONTEXT]:\n{rag_context}"
            )

        # 3. Instantiate LLM Provider dynamically via Factory Pattern
        provider = LLMProviderFactory.get_provider(provider_type=model_name)

        # 4. Stream response from selected LLM Provider
        try:
            async for chunk in provider.generate_stream(
                prompt=prompt,
                system_prompt=system_prompt,
                history=chat_history,
                temperature=0.2,
            ):
                yield chunk
        except Exception as e:
            print(f"❌ AIService Stream Error: {e}")
            yield f"\n[System Error: {self._fallback()}]"

    async def generate_chat_title(
        self, prompt: str, model_name: str = ModelProviderEnum.OLLAMA_LLAMA
    ) -> str:
        provider = LLMProviderFactory.get_provider(provider_type=model_name)
        try:
            res = await provider.generate_response(
                prompt=f"Generate a concise 3-4 word title for this conversation context: '{prompt}'. Return ONLY the title text.",
                temperature=0.3,
            )
            return res.strip().replace('"', "") if res else prompt[:25]
        except Exception:
            return prompt[:25]
