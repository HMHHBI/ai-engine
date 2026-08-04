from enum import Enum
# Factory file me app.services.providers... ki jagah relative imports:
from .base_provider import BaseLLMProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

class ModelProviderEnum(str, Enum):
    OLLAMA_LLAMA = "ollama-llama3.2"
    OLLAMA_DEEPSEEK = "ollama-deepseek-r1"
    GEMINI_FLASH = "gemini-2.5-flash"
    OPENAI_GPT4O = "openai-gpt-4o-mini"


class LLMProviderFactory:
    """Factory responsible for instantiating the requested LLM provider strategy."""

    @staticmethod
    def get_provider(
        provider_type: str = ModelProviderEnum.OLLAMA_LLAMA,
    ) -> BaseLLMProvider:
        if provider_type == ModelProviderEnum.OLLAMA_LLAMA:
            return OllamaProvider(model_name="llama3.2")
        elif provider_type == ModelProviderEnum.OLLAMA_DEEPSEEK:
            return OllamaProvider(model_name="deepseek-r1")
        elif provider_type == ModelProviderEnum.GEMINI_FLASH:
            return GeminiProvider(model_name="gemini-2.5-flash")
        elif provider_type == ModelProviderEnum.OPENAI_GPT4O:
            return OpenAIProvider(model_name="gpt-4o-mini")
        else:
            # Fallback to local Ollama default
            return OllamaProvider(model_name="llama3.2")
