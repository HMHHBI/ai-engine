from __future__ import annotations

from dataclasses import dataclass

from app.core.config import AIModel, AIProvider
from app.services.providers.base_provider import BaseLLMProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.ollama_provider import OllamaProvider
from app.services.providers.openai_provider import OpenAIProvider


@dataclass(frozen=True)
class ModelDefinition:
    provider: AIProvider
    model: AIModel


MODEL_REGISTRY: dict[AIModel, ModelDefinition] = {
    AIModel.OLLAMA_LLAMA_3_2: ModelDefinition(
        provider=AIProvider.OLLAMA,
        model=AIModel.OLLAMA_LLAMA_3_2,
    ),
    AIModel.OLLAMA_DEEPSEEK_R1: ModelDefinition(
        provider=AIProvider.OLLAMA,
        model=AIModel.OLLAMA_DEEPSEEK_R1,
    ),
    AIModel.GEMINI_2_5_FLASH: ModelDefinition(
        provider=AIProvider.GEMINI,
        model=AIModel.GEMINI_2_5_FLASH,
    ),
    AIModel.OPENAI_GPT_4O_MINI: ModelDefinition(
        provider=AIProvider.OPENAI,
        model=AIModel.OPENAI_GPT_4O_MINI,
    ),
}


class LLMProviderFactory:
    """
    Creates an LLM provider only when the provider/model combination
    is explicitly supported.

    Provider and model are deliberately validated independently.
    """

    @staticmethod
    def get_provider(
        provider: AIProvider | str,
        model: AIModel | str,
    ) -> BaseLLMProvider:
        provider = LLMProviderFactory._normalize_provider(provider)
        model = LLMProviderFactory._normalize_model(model)

        definition = MODEL_REGISTRY.get(model)

        if definition is None:
            raise ValueError(f"Unsupported AI model: '{model.value}'.")

        if definition.provider != provider:
            raise ValueError(
                f"Invalid AI provider/model combination: "
                f"provider='{provider.value}', "
                f"model='{model.value}'. "
                f"Expected provider='{definition.provider.value}'."
            )

        if provider == AIProvider.OLLAMA:
            return OllamaProvider(
                model_name=model.value,
            )

        if provider == AIProvider.GEMINI:
            return GeminiProvider(
                model_name=model.value,
            )

        if provider == AIProvider.OPENAI:
            return OpenAIProvider(
                model_name=model.value,
            )

        # This should be unreachable because AIProvider is an enum.
        raise ValueError(f"Unsupported AI provider: '{provider.value}'.")

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
                f"Unsupported AI provider '{provider}'. "
                f"Supported providers: {valid}."
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
                f"Unsupported AI model '{model}'. " f"Supported models: {valid}."
            ) from exc

    @staticmethod
    def get_supported_models(
        provider: AIProvider | str | None = None,
    ) -> list[AIModel]:
        """
        Return supported models.

        If provider is supplied, only models belonging to that provider
        are returned.
        """

        if provider is None:
            return list(MODEL_REGISTRY.keys())

        provider = LLMProviderFactory._normalize_provider(provider)

        return [
            model
            for model, definition in MODEL_REGISTRY.items()
            if definition.provider == provider
        ]

    @staticmethod
    def validate_configuration(
        provider: AIProvider | str,
        model: AIModel | str,
    ) -> tuple[AIProvider, AIModel]:
        """
        Validate provider/model without constructing a provider.

        Useful for API request validation and chat configuration updates.
        """

        normalized_provider = LLMProviderFactory._normalize_provider(provider)
        normalized_model = LLMProviderFactory._normalize_model(model)

        definition = MODEL_REGISTRY.get(normalized_model)

        if definition is None:
            raise ValueError(f"Unsupported AI model: '{normalized_model.value}'.")

        if definition.provider != normalized_provider:
            raise ValueError(
                f"Model '{normalized_model.value}' belongs to "
                f"provider '{definition.provider.value}', not "
                f"'{normalized_provider.value}'."
            )

        return normalized_provider, normalized_model
