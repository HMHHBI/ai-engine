from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from app.repositories.chat_repo import (
    SOURCE_SNIPPET_MAX_CHARS,
    ChatRepository,
    _normalize_sources,
    normalize_source_snippet,
)
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository


@dataclass
class DummyChunk:
    text: str
    page_number: int
    chunk_index: int


def test_source_snippet_normalizes_whitespace():
    value = "  First line.\n\nSecond\tline.   Third line.  "

    assert normalize_source_snippet(value) == (
        "First line. Second line. Third line."
    )


def test_source_snippet_is_bounded():
    value = "x" * (SOURCE_SNIPPET_MAX_CHARS + 100)

    snippet = normalize_source_snippet(value)

    assert snippet is not None
    assert len(snippet) == SOURCE_SNIPPET_MAX_CHARS
    assert snippet.endswith("…")
    assert snippet[:-1] == "x" * (SOURCE_SNIPPET_MAX_CHARS - 1)


def test_missing_chunk_content_produces_no_snippet():
    assert normalize_source_snippet(None) is None
    assert normalize_source_snippet("") is None
    assert normalize_source_snippet("   \n\t ") is None


def test_normalize_sources_preserves_real_snippet():
    sources = _normalize_sources(
        [
            {
                "id": 10,
                "document_id": 20,
                "page_number": 4,
                "chunk_index": 3,
                "distance": 0.123456789,
                "snippet": "  Actual document passage.\nWith spacing. ",
            }
        ]
    )

    assert sources == [
        {
            "id": 10,
            "document_id": 20,
            "page_number": 4,
            "chunk_index": 3,
            "distance": 0.123457,
            "snippet": "Actual document passage. With spacing.",
        }
    ]


def test_normalize_sources_gracefully_handles_missing_snippet():
    sources = _normalize_sources(
        [
            {
                "id": 10,
                "document_id": 20,
                "page_number": 4,
                "chunk_index": 3,
                "distance": 0.1,
            }
        ]
    )

    assert sources is not None
    assert sources[0]["snippet"] is None


def test_source_snippet_persistence_remains_chat_tenant_scoped(db_session):
    ts = int(time.time() * 1000)

    user_a = UserRepository.create(
        db_session,
        name="Evidence User A",
        email=f"evidence-a-{ts}@example.com",
        password="Password!123",
    )

    user_b = UserRepository.create(
        db_session,
        name="Evidence User B",
        email=f"evidence-b-{ts}@example.com",
        password="Password!123",
    )

    chat_a = ChatRepository.create_chat(user_id=user_a.id)
    chat_b = ChatRepository.create_chat(user_id=user_b.id)

    document_a = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="tenant-a.pdf",
        mime_type="application/pdf",
        file_size=100,
    )

    document_b = DocumentRepository.create(
        user_id=user_b.id,
        chat_id=chat_b.id,
        filename="tenant-b.pdf",
        mime_type="application/pdf",
        file_size=100,
    )

    assert document_a is not None
    assert document_b is not None

    vector = [0.1] * 768

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        chunks_with_embeddings=[
            (
                DummyChunk(
                    text="Tenant A confidential evidence.",
                    page_number=2,
                    chunk_index=0,
                ),
                vector,
            )
        ],
    )

    assert (
        VectorRepository.search_similar_chunks(
            user_id=user_a.id,
            document_id=document_a.id,
            query_vector=vector,
        )[0]["content"]
        == "Tenant A confidential evidence."
    )

    assert (
        VectorRepository.search_similar_chunks(
            user_id=user_b.id,
            document_id=document_a.id,
            query_vector=vector,
        )
        == []
    )

    assert (
        VectorRepository.search_similar_chunks(
            user_id=user_a.id,
            document_id=document_b.id,
            query_vector=vector,
        )
        == []
    )
