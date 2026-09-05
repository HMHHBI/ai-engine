from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# AI Stream Request Schema
class AIRequest(BaseModel):
    chat_id: int
    prompt: str
    task: str = "general"
    model: Optional[str] = None
    provider: Optional[str] = None
    file_context: Optional[str] = None
    image_base64: Optional[List[str]] = None
    image_mime: Optional[List[str]] = None


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
