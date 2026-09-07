from __future__ import annotations

import time
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch
import pytest

from app.core.security import create_access_token
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
def setup_user_and_populated_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Ingestion User",
        email=f"ingest-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)

    # Create initial document for the pre-populated chunks
    initial_doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="old_doc.pdf",
        mime_type="application/pdf",
        file_size=100,
    )
    assert initial_doc is not None

    # Pre-populate with initial valid document chunks
    initial_chunks = [
        (
            DummyChunk(
                text="Initial Old Document Content 1", page_number=1, chunk_index=0
            ),
            [0.1] * 768,
        ),
        (
            DummyChunk(
                text="Initial Old Document Content 2", page_number=1, chunk_index=1
            ),
            [0.2] * 768,
        ),
    ]
    VectorRepository.replace_document_chunks(
        user_id=user.id,
        document_id=initial_doc.id,
        chunks_with_embeddings=initial_chunks,
        pdf_context="Indexed File: old_doc.pdf",
    )

    return user, chat, initial_doc


def upload_text(client, chat_id: int, text_content: str, token: str):
    return client.post(
        f"/chat/upload-pdf/{chat_id}",
        files={
            "file": ("new_doc.txt", BytesIO(text_content.encode("utf-8")), "text/plain")
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def test_successful_replacement_replaces_old_vectors(
    client, setup_user_and_populated_chat
):
    user, chat, initial_doc = setup_user_and_populated_chat
    token = create_access_token(user.id)

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding"
    ) as mock_embed:
        mock_embed.return_value = [0.9] * 768

        response = upload_text(
            client, chat.id, "New Brand Content That Overwrites", token
        )

        assert response.status_code == 200

        # Query newly created document
        docs = DocumentRepository.list_for_chat(chat_id=chat.id, user_id=user.id)
        latest_doc = docs[0]

        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            document_id=latest_doc.id,
            query_vector=[0.9] * 768,
        )
        assert len(results) > 0


def test_embedding_failure_preserves_existing_document(
    client, setup_user_and_populated_chat
):
    user, chat, initial_doc = setup_user_and_populated_chat
    token = create_access_token(user.id)

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding"
    ) as mock_embed:
        mock_embed.return_value = None

        response = upload_text(client, chat.id, "Should Fail Ingestion Content", token)

        assert response.status_code == 502
        assert "Existing document was not changed" in response.json()["detail"]

        # Verify previous chunks remain untouched on the original document
        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            document_id=initial_doc.id,
            query_vector=[0.1] * 768,
        )
        assert len(results) == 2


def test_partial_embedding_failure_aborts_all_or_nothing(
    client, setup_user_and_populated_chat
):
    user, chat, initial_doc = setup_user_and_populated_chat
    token = create_access_token(user.id)

    long_text = (
        ("Chunk one text paragraph here. " * 30)
        + "\n\n"
        + ("Chunk two text paragraph here. " * 30)
    )

    call_count = 0

    async def mock_partial_failure(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [0.5] * 768
        return None

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        side_effect=mock_partial_failure,
    ):
        response = upload_text(client, chat.id, long_text, token)
        assert response.status_code == 502

        # Verify old vectors are still preserved
        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            document_id=initial_doc.id,
            query_vector=[0.1] * 768,
        )
        assert len(results) == 2
