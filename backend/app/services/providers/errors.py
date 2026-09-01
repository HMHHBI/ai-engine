from __future__ import annotations


class AIProviderError(Exception):
    """Base class for provider failures."""

    def __init__(
        self,
        message: str = "AI provider request failed.",
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable


class AIProviderConfigurationError(AIProviderError):
    """Provider cannot operate because its configuration is invalid."""


class AIProviderTimeout(AIProviderError):
    """Provider exceeded its configured timeout."""

    def __init__(
        self,
        message: str = "AI provider request timed out.",
    ) -> None:
        super().__init__(message, retryable=True)


class AIProviderUnavailable(AIProviderError):
    """Provider is temporarily unavailable."""

    def __init__(
        self,
        message: str = "AI provider is temporarily unavailable.",
    ) -> None:
        super().__init__(message, retryable=True)


class AIProviderResponseError(AIProviderError):
    """Provider returned an invalid or unusable response."""

    def __init__(
        self,
        message: str = "AI provider returned an invalid or unusable response.",
    ) -> None:
        super().__init__(message, retryable=True)
