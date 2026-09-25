from __future__ import annotations

from io import BytesIO
import time
from unittest.mock import patch

import pytest

from app.core.config import EmbeddingProvider
from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_job_repo import DocumentJobRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.services.embedding_service import DocumentChunk


def auth_headers(user):
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )

    return {
        "Authorization": f"Bearer {token}",
    }


@pytest.fixture()
def lifecycle_user_and_chat(db_session):
    ts = int(time.time() * 1000)

    user = UserRepository.create(
        db_session,
        name="Lifecycle User",
        email=f"lifecycle-{ts}@example.com",
        password="Password!123",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
    )

    return user, chat


def test_document_lifecycle_upload_creates_durable_job_and_ready_document(
    client,
    lifecycle_user_and_chat,
):
    user, chat = lifecycle_user_and_chat

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ):
        response = client.post(
            f"/documents/chat/{chat.id}/upload",
            files={
                "file": (
                    "research.txt",
                    BytesIO(
                        b"Research evidence that should be indexed."
                    ),
                    "text/plain",
                )
            },
            headers=auth_headers(user),
        )

    assert response.status_code == 201

    body = response.json()

    assert body["status"] == "ready"
    assert body["filename"] == "research.txt"
    assert body["job"]["status"] == "ready"
    assert body["job"]["attempt"] == 1

    document = DocumentRepository.get_owned_document(
        document_id=body["id"],
        user_id=user.id,
    )

    assert document is not None
    assert document.status == "ready"
    assert body["job"]["document_id"] == document.id


def test_failed_document_is_retained_and_retryable(
    client,
    lifecycle_user_and_chat,
):
    user, chat = lifecycle_user_and_chat

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=None,
    ):
        response = client.post(
            f"/documents/chat/{chat.id}/upload",
            files={
                "file": (
                    "retryable.txt",
                    BytesIO(
                        b"Content that will initially fail embedding."
                    ),
                    "text/plain",
                )
            },
            headers=auth_headers(user),
        )

    assert response.status_code == 500

    documents = DocumentRepository.list_for_chat(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert len(documents) == 1
    document = documents[0]

    assert document.status == "failed"
    assert document.storage_key is not None

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.2] * 768,
    ):
        retry_response = client.post(
            f"/documents/{document.id}/retry",
            headers=auth_headers(user),
        )

    assert retry_response.status_code == 200

    retry_body = retry_response.json()

    assert retry_body["id"] == document.id
    assert retry_body["status"] == "ready"
    assert retry_body["job"]["status"] == "ready"
    assert retry_body["job"]["attempt"] == 1


def test_retry_cross_user_document_is_rejected(
    client,
    lifecycle_user_and_chat,
    db_session,
):
    user_a, chat_a = lifecycle_user_and_chat

    ts = int(time.time() * 1000)

    user_b = UserRepository.create(
        db_session,
        name="Other User",
        email=f"other-lifecycle-{ts}@example.com",
        password="Password!123",
    )

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=None,
    ):
        response = client.post(
            f"/documents/chat/{chat_a.id}/upload",
            files={
                "file": (
                    "private.txt",
                    BytesIO(b"private content"),
                    "text/plain",
                )
            },
            headers=auth_headers(user_a),
        )

    assert response.status_code == 500

    document = DocumentRepository.list_for_chat(
        chat_id=chat_a.id,
        user_id=user_a.id,
    )[0]

    response = client.post(
        f"/documents/{document.id}/retry",
        headers=auth_headers(user_b),
    )

    assert response.status_code == 404


def test_failed_document_cannot_be_selected_as_ready_document(
    lifecycle_user_and_chat,
):
    user, chat = lifecycle_user_and_chat

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="failed.pdf",
        mime_type="application/pdf",
        status="failed",
    )

    assert document is not None

    ready = DocumentRepository.get_ready_for_chat(
        document_id=document.id,
        chat_id=chat.id,
        user_id=user.id,
    )

    assert ready is None


def test_document_list_exposes_granular_lifecycle_state(
    client,
    lifecycle_user_and_chat,
):
    user, chat = lifecycle_user_and_chat

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="processing.pdf",
        mime_type="application/pdf",
        status="indexing",
    )

    assert document is not None

    response = client.get(
        f"/documents/chat/{chat.id}",
        headers=auth_headers(user),
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["status"] == "indexing"
