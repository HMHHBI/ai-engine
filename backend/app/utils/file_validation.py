from __future__ import annotations

from pathlib import PurePath
from fastapi import HTTPException, UploadFile, status
from app.core.config import settings

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".json",
}

ALLOWED_CONTENT_TYPES = {
    ".pdf": {
        "application/pdf",
    },
    ".txt": {
        "text/plain",
    },
    ".md": {
        "text/markdown",
        "text/plain",
    },
    ".json": {
        "application/json",
        "text/json",
        "text/plain",
    },
}


def sanitize_filename(filename: str | None) -> str:
    """Return a safe bounded display filename."""
    if not filename:
        return "uploaded-file"

    name = PurePath(filename).name
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        return "uploaded-file"

    return name[:255]


def get_extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def validate_extension(filename: str) -> str:
    extension = get_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file format. Allowed formats: .pdf, .txt, .md, .json.",
        )
    return extension


def validate_content_type(extension: str, content_type: str | None) -> None:
    if not content_type:
        return

    normalized = content_type.split(";", 1)[0].strip().lower()
    allowed = ALLOWED_CONTENT_TYPES.get(extension, set())

    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content type does not match its extension.",
        )


def validate_pdf_signature(content: bytes) -> None:
    if len(content) < 5 or content[:5] != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File is not a valid PDF.",
        )


async def read_upload_with_limit(
    file: UploadFile, *, max_bytes: int | None = None
) -> bytes:
    limit = max_bytes or settings.MAX_UPLOAD_SIZE_BYTES
    if limit <= 0:
        raise RuntimeError("MAX_UPLOAD_SIZE_BYTES must be positive.")

    content = await file.read(limit + 1)

    if len(content) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the maximum allowed size of {limit} bytes.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty.",
        )

    return content
