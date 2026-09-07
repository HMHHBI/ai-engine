from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.core.security import create_access_token
from app.db.models import Chat
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture()
def user_and_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Chat Doc User",
        email=f"doc-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    # Enable document RAG pipeline for this chat
    chat.pdf_context = "Indexed Document: context.pdf"
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_embedding_and_vector():
    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new_callable=AsyncMock,
    ) as mock_embed, patch(
        "app.repositories.vector_repo.VectorRepository.search_similar_chunks"
    ) as mock_search, patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider"
    ) as mock_provider_factory:
        mock_embed.return_value = [0.1] * 768
        mock_search.return_value = [
            {
                "id": 101,
                "content": "Test retrieved document chunk content.",
                "page_number": 1,
                "chunk_index": 0,
                "distance": 0.15,
            }
        ]

        class DummyProvider:
            async def generate_stream(self, *args, **kwargs):
                yield "Test response token."

        mock_provider_factory.return_value = DummyProvider()

        yield {
            "embed": mock_embed,
            "search": mock_search,
        }


def test_stream_with_explicit_ready_document(
    client,
    user_and_chat,
):
    user, chat = user_and_chat
    headers = auth_headers(user)

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="doc1.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc.id, user_id=user.id, status="ready"
    )

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "Summarize this document",
            "document_id": doc.id,
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_200_OK
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_stream_explicit_document_rejects_nonexistent(
    client,
    user_and_chat,
):
    user, chat = user_and_chat
    headers = auth_headers(user)

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "Hello",
            "document_id": 99999999,
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Document not found."


def test_stream_explicit_document_rejects_processing_status(
    client,
    user_and_chat,
):
    user, chat = user_and_chat
    headers = auth_headers(user)

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="processing.pdf",
        mime_type="application/pdf",
    )

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "Hello",
            "document_id": doc.id,
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Document not found."


def test_stream_explicit_document_rejects_failed_status(
    client,
    user_and_chat,
):
    user, chat = user_and_chat
    headers = auth_headers(user)

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="failed.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc.id,
        user_id=user.id,
        status="failed",
        error_message="Ingestion failure",
    )

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "Hello",
            "document_id": doc.id,
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Document not found."


def test_stream_explicit_document_rejects_cross_chat_document(
    client,
    db_session,
    user_and_chat,
):
    user, chat_a = user_and_chat
    headers = auth_headers(user)
    chat_b = ChatRepository.create_chat(user_id=user.id)
    chat_b.pdf_context = "Indexed Document: doc_b.pdf"
    db_session.add(chat_b)
    db_session.commit()

    doc_a = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat_a.id,
        filename="doc_a.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc_a.id, user_id=user.id, status="ready"
    )

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat_b.id,
            "prompt": "Hello",
            "document_id": doc_a.id,
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Document not found."


def test_stream_explicit_document_rejects_cross_user_document(
    client,
    db_session,
    user_and_chat,
):
    user_a, chat_a = user_and_chat
    headers_a = auth_headers(user_a)

    ts = int(time.time() * 1000)
    user_b = UserRepository.create(
        db_session,
        name="User B",
        email=f"user-b-b6-{ts}@example.com",
        password="Password!123",
    )
    chat_b = ChatRepository.create_chat(user_id=user_b.id)

    doc_b = DocumentRepository.create(
        user_id=user_b.id,
        chat_id=chat_b.id,
        filename="doc_b.pdf",
        mime_type="application/pdf",
    )
    DocumentRepository.update_status(
        document_id=doc_b.id, user_id=user_b.id, status="ready"
    )

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat_a.id,
            "prompt": "Hello",
            "document_id": doc_b.id,
        },
        headers=headers_a,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Document not found."
