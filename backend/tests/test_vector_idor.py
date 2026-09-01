from __future__ import annotations

import time
from dataclasses import dataclass
import pytest

from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository


@dataclass
class DummyChunk:
    text: str
    page_number: int
    chunk_index: int


@pytest.fixture()
def two_users_and_chats(db_session):
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

    return user_a, user_b, chat_a, chat_b


def test_user_a_can_store_and_search_own_vectors(two_users_and_chats):
    user_a, _, chat_a, _ = two_users_and_chats
    dummy_vec = [0.1] * 768
    chunks = [
        (DummyChunk(text="Secret Document A", page_number=1, chunk_index=0), dummy_vec)
    ]

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        chat_id=chat_a.id,
        chunks_with_embeddings=chunks,
    )

    results = VectorRepository.search_similar_chunks(
        user_id=user_a.id,
        chat_id=chat_a.id,
        query_vector=dummy_vec,
    )

    assert len(results) == 1
    assert results[0]["content"] == "Secret Document A"


def test_user_b_cannot_search_user_a_vectors(two_users_and_chats):
    user_a, user_b, chat_a, _ = two_users_and_chats
    dummy_vec = [0.1] * 768
    chunks = [
        (
            DummyChunk(text="Confidential Financials", page_number=1, chunk_index=0),
            dummy_vec,
        )
    ]

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        chat_id=chat_a.id,
        chunks_with_embeddings=chunks,
    )

    # User B queries User A's chat
    results = VectorRepository.search_similar_chunks(
        user_id=user_b.id,
        chat_id=chat_a.id,
        query_vector=dummy_vec,
    )

    assert results == []


def test_user_b_cannot_insert_vectors_into_user_a_chat(two_users_and_chats):
    _, user_b, chat_a, _ = two_users_and_chats
    dummy_vec = [0.1] * 768
    chunks = [
        (
            DummyChunk(text="Malicious Injected Vector", page_number=1, chunk_index=0),
            dummy_vec,
        )
    ]

    with pytest.raises(LookupError, match="Chat not found"):
        VectorRepository.store_document_chunks(
            user_id=user_b.id,
            chat_id=chat_a.id,
            chunks_with_embeddings=chunks,
        )


def test_user_b_cannot_delete_user_a_vectors(two_users_and_chats):
    user_a, user_b, chat_a, _ = two_users_and_chats
    dummy_vec = [0.1] * 768
    chunks = [(DummyChunk(text="Data A", page_number=1, chunk_index=0), dummy_vec)]

    VectorRepository.store_document_chunks(
        user_id=user_a.id,
        chat_id=chat_a.id,
        chunks_with_embeddings=chunks,
    )

    # Attempt delete by User B
    deleted = VectorRepository.delete_document_chunks(
        user_id=user_b.id,
        chat_id=chat_a.id,
    )
    assert deleted is False

    # Verify User A's data is still intact
    results = VectorRepository.search_similar_chunks(
        user_id=user_a.id,
        chat_id=chat_a.id,
        query_vector=dummy_vec,
    )
    assert len(results) == 1
