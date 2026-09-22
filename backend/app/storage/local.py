from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.core.config import settings
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """
    Filesystem-backed storage implementation for local dev and tests.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root if root is not None else settings.LOCAL_STORAGE_ROOT
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, key: str) -> Path:
        normalized_key = key.strip().replace("\\", "/")
        if not normalized_key:
            raise ValueError("Storage key cannot be empty.")

        path = (self.root / normalized_key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError("Storage key escapes the storage root.")

        return path

    def save(
        self,
        key: str,
        stream: BinaryIO,
        *,
        content_type: str,
    ) -> str:
        del content_type
        path = self._resolve_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("wb") as destination:
            while chunk := stream.read(1024 * 1024):
                destination.write(chunk)

        return key

    def get_stream(
        self,
        key: str,
    ) -> BinaryIO:
        path = self._resolve_key(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.open("rb")

    def delete(
        self,
        key: str,
    ) -> None:
        path = self._resolve_key(key)
        if path.exists():
            path.unlink()

    def exists(
        self,
        key: str,
    ) -> bool:
        return self._resolve_key(key).is_file()
