from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ResearchStatus = Literal["queued", "running", "completed", "failed"]


class ResearchRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    document_ids: list[int] = Field(min_length=2, max_length=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Query cannot be blank.")
        return value

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, value: list[int]) -> list[int]:
        if any(document_id <= 0 for document_id in value):
            raise ValueError("Document IDs must be positive integers.")
        if len(set(value)) != len(value):
            raise ValueError("Document IDs must not contain duplicates.")
        return value


class ResearchCitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(pattern=r"^C[1-9][0-9]*$")
    document_id: int
    filename: str
    chunk_id: int
    page_number: int | None = None
    excerpt: str = Field(min_length=1, max_length=1200)


class ResearchFacetsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methodology: str = Field(min_length=1)
    datasets: str = Field(min_length=1)
    metrics: str = Field(min_length=1)
    findings: str = Field(min_length=1)
    limitations: str = Field(min_length=1)


class ResearchRunCreateOut(BaseModel):
    id: int
    workspace_id: int
    requester_id: int
    query: str
    status: ResearchStatus
    answer: str | None = None
    facets: ResearchFacetsOut | None = None
    citations: list[ResearchCitationOut] = Field(default_factory=list)
    run_metadata: dict = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None


class ResearchRunOut(ResearchRunCreateOut):
    error_message: str | None = None


class ResearchRunListOut(BaseModel):
    items: list[ResearchRunOut]
    total: int
