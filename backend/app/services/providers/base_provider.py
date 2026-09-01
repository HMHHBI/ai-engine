from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List, Optional


class BaseLLMProvider(ABC):

    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        """Generate a complete non-streaming response."""
        raise NotImplementedError

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """Generate a cancellable asynchronous token stream."""
        raise NotImplementedError
