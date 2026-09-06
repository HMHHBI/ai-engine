from __future__ import annotations

from dataclasses import dataclass
import time

import pytest

from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository


@dataclass
class DummyChunk:
    text: str
    page_number: int
    chunk_index: int


@pytest.fixture()
def two_users_and_documents(db_session):
    ts = int(time.time() * 1000)

    user_a = UserRepository.create(
        db_session,
        name="Tenant A",
        email=f"vec-a-{ts}@example.com",
        password="Password!123",
    )

    user_b = UserRepository.create(
        db_session,
        name="Tenant B",
        email=f"vec-b-{ts}@example.com",
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

    return (
        user_a,
        user_b,
        chat_a,
        chat_b,
        document_a,
        document_b,
    )


def test_user_a_can_store_and_search_own_vectors(two_users_and_documents):
    (
        user_a,
        _,
        _,
        _,
        document_a,
        _,
    ) = two_users_and_documents

    dummy_vec = [0.1] * 768

    chunks = [
        (
            DummyChunk(
                text="Secret Document A",
                page_number=1,
                chunk_index=0,
            ),
            dummy_vec,
        )
    ]

    stored = VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        chunks_with_embeddings=chunks,
    )

    assert len(stored) == 1
    assert stored[0]["document_id"] == document_a.id

    results = VectorRepository.search_similar_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        query_vector=dummy_vec,
    )

    assert len(results) == 1
    assert results[0]["content"] == "Secret Document A"
    assert results[0]["document_id"] == document_a.id
    assert results[0]["chat_id"] == document_a.chat_id


def test_user_b_cannot_search_user_a_document(two_users_and_documents):
    (
        user_a,
        user_b,
        _,
        _,
        document_a,
        _,
    ) = two_users_and_documents

    dummy_vec = [0.1] * 768

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        chunks_with_embeddings=[
            (
                DummyChunk(
                    text="Confidential Financials",
                    page_number=1,
                    chunk_index=0,
                ),
                dummy_vec,
            )
        ],
    )

    results = VectorRepository.search_similar_chunks(
        user_id=user_b.id,
        document_id=document_a.id,
        query_vector=dummy_vec,
    )

    assert results == []


def test_user_b_cannot_insert_vectors_into_user_a_document(two_users_and_documents):
    (
        _,
        user_b,
        _,
        _,
        document_a,
        _,
    ) = two_users_and_documents

    dummy_vec = [0.1] * 768

    chunks = [
        (
            DummyChunk(
                text="Malicious Injected Vector",
                page_number=1,
                chunk_index=0,
            ),
            dummy_vec,
        )
    ]

    with pytest.raises(LookupError, match="Document not found"):
        VectorRepository.store_document_chunks(
            user_id=user_b.id,
            document_id=document_a.id,
            chunks_with_embeddings=chunks,
        )


def test_user_b_cannot_delete_user_a_document_vectors(two_users_and_documents):
    (
        user_a,
        user_b,
        _,
        _,
        document_a,
        _,
    ) = two_users_and_documents

    dummy_vec = [0.1] * 768

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        chunks_with_embeddings=[
            (
                DummyChunk(
                    text="Data A",
                    page_number=1,
                    chunk_index=0,
                ),
                dummy_vec,
            )
        ],
    )

    deleted = VectorRepository.delete_document_chunks(
        user_id=user_b.id,
        document_id=document_a.id,
    )

    assert deleted is False

    results = VectorRepository.search_similar_chunks(
        user_id=user_a.id,
        document_id=document_a.id,
        query_vector=dummy_vec,
    )

    assert len(results) == 1
    assert results[0]["content"] == "Data A"


def test_document_vector_access_requires_dual_ownership(
    two_users_and_documents,
    db_session,
):
    (
        user_a,
        user_b,
        _,
        chat_b,
        document_a,
        _,
    ) = two_users_and_documents

    # Directly update in DB so session isolation doesn't mask the change
    from sqlalchemy import update
    from app.db.models import Document

    db_session.execute(
        update(Document).where(Document.id == document_a.id).values(chat_id=chat_b.id)
    )
    db_session.commit()

    dummy_vec = [0.1] * 768

    with pytest.raises(LookupError, match="Document not found"):
        VectorRepository.store_document_chunks(
            user_id=user_a.id,
            document_id=document_a.id,
            chunks_with_embeddings=[
                (
                    DummyChunk(
                        text="Should never be inserted",
                        page_number=1,
                        chunk_index=0,
                    ),
                    dummy_vec,
                )
            ],
        )

    assert (
        VectorRepository.search_similar_chunks(
            user_id=user_a.id,
            document_id=document_a.id,
            query_vector=dummy_vec,
        )
        == []
    )
