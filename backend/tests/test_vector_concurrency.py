from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time

import pytest
from sqlalchemy import text

from app.db.models import DocumentChunk
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository


@dataclass
class DummyChunk:
    text: str
    page_number: int
    chunk_index: int


def make_chunk(text: str, index: int, page: int = 1) -> DummyChunk:
    return DummyChunk(text=text, page_number=page, chunk_index=index)


@pytest.fixture()
def vector_document(db_session):
    timestamp = int(time.time() * 1000000)

    user = UserRepository.create(
        db_session,
        name="Vector Concurrency User",
        email=f"vector-concurrency-{timestamp}@example.com",
        password="Password!123",
    )

    chat = ChatRepository.create_chat(user_id=user.id)

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="concurrency.pdf",
        mime_type="application/pdf",
        file_size=100,
    )

    assert document is not None

    return user, chat, document


def test_concurrent_replacements_are_serialized(vector_document, monkeypatch):
    user, chat, document = vector_document

    embedding_a = [0.1] * 768
    embedding_b = [0.2] * 768

    first_chunks = [
        (make_chunk("document-a-1", 0), embedding_a),
        (make_chunk("document-a-2", 1), embedding_a),
    ]

    second_chunks = [
        (make_chunk("document-b-1", 0), embedding_b),
        (make_chunk("document-b-2", 1), embedding_b),
        (make_chunk("document-b-3", 2), embedding_b),
    ]

    def run_first():
        return VectorRepository.replace_document_chunks(
            user_id=user.id,
            document_id=document.id,
            chunks_with_embeddings=first_chunks,
            pdf_context="document-a",
        )

    def run_second():
        return VectorRepository.replace_document_chunks(
            user_id=user.id,
            document_id=document.id,
            chunks_with_embeddings=second_chunks,
            pdf_context="document-b",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_first)
        f2 = executor.submit(run_second)
        f1.result()
        f2.result()

    with session_scope() as db:
        chunks = list(
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    assert all(chunk.chat_id == chat.id for chunk in chunks)
    assert all(chunk.document_id == document.id for chunk in chunks)

    contents = [chunk.content for chunk in chunks]
    assert contents in [
        ["document-a-1", "document-a-2"],
        ["document-b-1", "document-b-2", "document-b-3"],
    ]


def test_replacement_is_scoped_to_document(db_session):
    timestamp = int(time.time() * 1000000)

    user = UserRepository.create(
        db_session,
        name="Vector Isolation User",
        email=f"vector-isolation-{timestamp}@example.com",
        password="Password!123",
    )

    chat = ChatRepository.create_chat(user_id=user.id)

    document_a = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="document-a.pdf",
        mime_type="application/pdf",
        file_size=100,
    )

    document_b = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="document-b.pdf",
        mime_type="application/pdf",
        file_size=100,
    )

    assert document_a is not None
    assert document_b is not None

    embedding = [0.0] * 768

    VectorRepository.store_document_chunks(
        user_id=user.id,
        document_id=document_a.id,
        chunks_with_embeddings=[
            (make_chunk("A-1", 0), embedding),
            (make_chunk("A-2", 1), embedding),
        ],
    )

    VectorRepository.store_document_chunks(
        user_id=user.id,
        document_id=document_b.id,
        chunks_with_embeddings=[
            (make_chunk("B-1", 0), embedding),
        ],
    )

    VectorRepository.replace_document_chunks(
        user_id=user.id,
        document_id=document_a.id,
        chunks_with_embeddings=[
            (make_chunk("A-new", 0), embedding),
        ],
        pdf_context="document-a-replaced",
    )

    with session_scope() as db:
        chunks_a = list(
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_a.id)
            .all()
        )

        chunks_b = list(
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_b.id)
            .all()
        )

    assert [chunk.content for chunk in chunks_a] == ["A-new"]
    assert [chunk.content for chunk in chunks_b] == ["B-1"]

    assert all(chunk.chat_id == chat.id for chunk in chunks_a + chunks_b)
    assert all(chunk.document_id == document_a.id for chunk in chunks_a)
    assert all(chunk.document_id == document_b.id for chunk in chunks_b)


def test_replacement_rolls_back_when_chunk_insertion_fails(
    vector_document, monkeypatch
):
    user, chat, document = vector_document

    embedding = [0.1] * 768
    original_chunks = [
        (make_chunk("original-1", 0), embedding),
        (make_chunk("original-2", 1), embedding),
    ]

    VectorRepository.replace_document_chunks(
        user_id=user.id,
        document_id=document.id,
        chunks_with_embeddings=original_chunks,
        pdf_context="original document",
    )

    # Trigger a real DB-level vector constraint violation (dimension mismatch: 10 vs 768)
    failing_chunks = [
        (make_chunk("new-1", 0), embedding),
        (make_chunk("new-2", 1), [0.1] * 10),
    ]

    with pytest.raises(Exception):
        VectorRepository.replace_document_chunks(
            user_id=user.id,
            document_id=document.id,
            chunks_with_embeddings=failing_chunks,
            pdf_context="new-document",
        )

    with session_scope() as db:
        chunks_after = list(
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    assert [chunk.content for chunk in chunks_after] == [
        "original-1",
        "original-2",
    ]
    assert all(chunk.chat_id == chat.id for chunk in chunks_after)
    assert all(chunk.document_id == document.id for chunk in chunks_after)
