from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.db.models import Document
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository


class DummyChunk:
    def __init__(self, text: str, page_number: int = 1, chunk_index: int = 0):
        self.text = text
        self.page_number = page_number
        self.chunk_index = chunk_index


@pytest.fixture()
def setup_user_and_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="RAG Test User",
        email=f"rag-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def test_get_active_for_chat_selects_latest_ready(setup_user_and_chat):
    user, chat = setup_user_and_chat

    # Doc 1: ready
    doc1 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc1.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc1.id, user_id=user.id, status="ready"
    )

    # Doc 2: ready (newer)
    doc2 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc2.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc2.id, user_id=user.id, status="ready"
    )

    # Doc 3: processing
    doc3 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc3.pdf",
        mime_type="application/pdf",
    )

    # Doc 4: failed
    doc4 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc4.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc4.id, user_id=user.id, status="failed", error_message="Failed"
    )

    active = DocumentRepository.get_active_for_chat(chat_id=chat.id, user_id=user.id)
    assert active is not None
    assert active.id == doc2.id
    assert active.status == "ready"


def test_get_active_for_chat_cross_user_isolation(setup_user_and_chat, db_session):
    user_a, chat_a = setup_user_and_chat

    doc_a = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="doc_a.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc_a.id, user_id=user_a.id, status="ready"
    )

    ts = int(time.time() * 1000)
    user_b = UserRepository.create(
        db_session,
        name="User B",
        email=f"rag-b-{ts}@example.com",
        password="Password!123",
    )

    # User B cannot resolve User A's chat document
    active = DocumentRepository.get_active_for_chat(
        chat_id=chat_a.id, user_id=user_b.id
    )
    assert active is None


def test_same_chat_multi_document_retrieval_isolation(setup_user_and_chat):
    user, chat = setup_user_and_chat

    doc1 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc1.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc1.id, user_id=user.id, status="ready"
    )

    doc2 = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc2.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc2.id, user_id=user.id, status="ready"
    )

    dummy_vec = [0.1] * 768

    VectorRepository.store_document_chunks(
        user_id=user.id,
        document_id=doc1.id,
        chunks_with_embeddings=[(DummyChunk("APPLE_SECRET", 1, 0), dummy_vec)],
    )

    VectorRepository.store_document_chunks(
        user_id=user.id,
        document_id=doc2.id,
        chunks_with_embeddings=[(DummyChunk("BANANA_SECRET", 1, 0), dummy_vec)],
    )

    active_doc = DocumentRepository.get_active_for_chat(
        chat_id=chat.id, user_id=user.id
    )
    assert active_doc.id == doc2.id

    results = VectorRepository.search_similar_chunks(
        user_id=user.id,
        document_id=active_doc.id,
        query_vector=dummy_vec,
    )

    contents = [r["content"] for r in results]
    assert "BANANA_SECRET" in contents
    assert "APPLE_SECRET" not in contents
