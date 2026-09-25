from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings


class AIRequest(BaseModel):
    chat_id: int = Field(gt=0)
    prompt: str = Field(
        min_length=1,
        max_length=settings.MAX_PROMPT_CHARS,
    )
    task: str = Field(default="general", max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=50)
    file_context: Optional[str] = Field(
        default=None,
        max_length=settings.MAX_FILE_CONTEXT_CHARS,
    )
    image_base64: Optional[List[str]] = Field(
        default=None,
        max_length=settings.MAX_IMAGE_COUNT,
    )
    image_mime: Optional[List[str]] = Field(
        default=None,
        max_length=settings.MAX_IMAGE_COUNT,
    )
    document_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt cannot be empty.")
        return value

    @field_validator("image_base64")
    @classmethod
    def validate_images(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value

        if len(value) > settings.MAX_IMAGE_COUNT:
            raise ValueError(f"Maximum {settings.MAX_IMAGE_COUNT} images are allowed.")

        total = 0
        for img in value:
            if not img or not img.strip():
                raise ValueError("Image payload cannot be empty.")
            if len(img) > settings.MAX_IMAGE_BASE64_CHARS:
                raise ValueError(
                    "Individual image payload exceeds maximum allowed size."
                )
            total += len(img)

        if total > settings.MAX_TOTAL_IMAGE_BASE64_CHARS:
            raise ValueError("Combined image payloads exceed maximum allowed size.")

        return value

    @field_validator("image_mime")
    @classmethod
    def validate_image_mimes(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value

        allowed = {"image/jpeg", "image/png", "image/webp"}
        for mime in value:
            if mime.lower() not in allowed:
                raise ValueError("Unsupported image type.")

        return value

    @model_validator(mode="after")
    def validate_image_payload_parity(self) -> AIRequest:
        has_images = bool(self.image_base64)
        has_mimes = bool(self.image_mime)

        if has_images != has_mimes:
            raise ValueError(
                "image_base64 and image_mime must both be provided together."
            )

        if has_images and has_mimes:
            if len(self.image_base64) != len(self.image_mime):
                raise ValueError(
                    "image_base64 and image_mime must contain the exact same number of items."
                )

        return self


class ChatCreate(BaseModel):
    title: Optional[str] = Field(default="New Chat", max_length=255)
    persona: str = Field(default="default", max_length=50)
    custom_instructions: Optional[str] = Field(default=None, max_length=2000)


class ChatPersonaUpdate(BaseModel):
    persona: Optional[str] = Field(default=None, max_length=50)
    custom_instructions: Optional[str] = Field(default=None, max_length=2000)


class RetrievedSourceOut(BaseModel):
    id: int
    document_id: Optional[int] = None
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    distance: float
    snippet: Optional[str] = Field(default=None, max_length=800)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    image_data: Optional[str] = None
    sources: Optional[List[RetrievedSourceOut]] = None


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    persona: str = "default"
    custom_instructions: Optional[str] = None


class ChatDetailsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    pdf_context: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    persona: str = "default"
    custom_instructions: Optional[str] = None
