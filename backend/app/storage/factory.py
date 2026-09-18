from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend
from app.storage.r2 import R2StorageBackend


@lru_cache(maxsize=1)
def get_storage_backend() -> StorageBackend:
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageBackend()
    if settings.STORAGE_BACKEND == "r2":
        return R2StorageBackend()
    raise ValueError(f"Unsupported STORAGE_BACKEND: {settings.STORAGE_BACKEND}")
