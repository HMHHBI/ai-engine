from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


# AI Stream Request Schema
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


# Create Chat Request Schema
class ChatCreate(BaseModel):
    title: Optional[str] = Field(default="New Chat", max_length=255)
    persona: str = Field(default="default", max_length=50)
    custom_instructions: Optional[str] = Field(default=None, max_length=2000)


# Update Persona / Instructions Request Schema
class ChatPersonaUpdate(BaseModel):
    persona: Optional[str] = Field(default=None, max_length=50)
    custom_instructions: Optional[str] = Field(default=None, max_length=2000)


# Message Out Schema (Hydrated History & Citations)
class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    image_data: Optional[str] = None
    sources: Optional[List[dict[str, Any]]] = None


# Chat Summary Schema (For Sidebar / List)
class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    persona: str = "default"
    custom_instructions: Optional[str] = None


# Chat Details Schema (Full metadata)
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
