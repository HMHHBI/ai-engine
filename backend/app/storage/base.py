from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    """
    Abstract interface for durable document/object storage.
    """

    @abstractmethod
    def save(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
    ) -> str:
        """Persist an object and return its storage key."""
        raise NotImplementedError

    @abstractmethod
    def get_stream(
        self,
        key: str,
    ) -> BinaryIO:
        """Return a readable binary stream for an existing object."""
        raise NotImplementedError

    @abstractmethod
    def delete(
        self,
        key: str,
    ) -> None:
        """Delete an object idempotently."""
        raise NotImplementedError

    @abstractmethod
    def exists(
        self,
        key: str,
    ) -> bool:
        """Return whether an object exists."""
        raise NotImplementedError
