from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    chat_id: int
    filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=1, max_length=100)
    file_size: Optional[int] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    storage_url: Optional[str] = None


class DocumentStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=20)
    error_message: Optional[str] = None


class DocumentMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
    )


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    chat_id: int
    filename: str
    mime_type: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    storage_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    filename: str
    mime_type: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DocumentJobOut(BaseModel):
    id: int
    document_id: int
    status: str
    attempt: int
    max_attempts: int
    error_message: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class DocumentLifecycleOut(DocumentOut):
    job: Optional[DocumentJobOut] = None
