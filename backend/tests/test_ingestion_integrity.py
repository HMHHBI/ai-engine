from __future__ import annotations

import time
from dataclasses import dataclass
from io import BytesIO
from unittest.mock import patch
import pytest

from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
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
        chat_id=chat.id,
        chunks_with_embeddings=initial_chunks,
        pdf_context="Indexed File: old_doc.pdf",
    )

    return user, chat


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
    user, chat = setup_user_and_populated_chat
    token = create_access_token(user.id)

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding"
    ) as mock_embed:
        mock_embed.return_value = [0.9] * 768

        response = upload_text(
            client, chat.id, "New Brand Content That Overwrites", token
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # Verify old vectors are gone and new vector exists
        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            chat_id=chat.id,
            query_vector=[0.9] * 768,
        )
        assert len(results) == 1
        assert "New Brand Content" in results[0]["content"]

        # Verify pdf_context updated
        updated_chat = ChatRepository.get_by_id(chat_id=chat.id, user_id=user.id)
        assert updated_chat.pdf_context == "Indexed File: new_doc.txt"


def test_embedding_failure_preserves_existing_document(
    client, setup_user_and_populated_chat
):
    user, chat = setup_user_and_populated_chat
    token = create_access_token(user.id)

    # Simulate failure on embedding generation
    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding"
    ) as mock_embed:
        mock_embed.return_value = None  # None indicates failure to produce vector

        response = upload_text(client, chat.id, "Should Fail Ingestion Content", token)

        assert response.status_code == 502
        assert "Existing document was not changed" in response.json()["detail"]

        # Verify previous chunks remain untouched
        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            chat_id=chat.id,
            query_vector=[0.1] * 768,
        )
        assert len(results) == 2
        assert "Initial Old Document" in results[0]["content"]

        # Verify previous pdf_context preserved
        preserved_chat = ChatRepository.get_by_id(chat_id=chat.id, user_id=user.id)
        assert preserved_chat.pdf_context == "Indexed File: old_doc.pdf"


def test_partial_embedding_failure_aborts_all_or_nothing(
    client, setup_user_and_populated_chat
):
    user, chat = setup_user_and_populated_chat
    token = create_access_token(user.id)

    # Multi-chunk text
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
        return None  # Second chunk fails

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        side_effect=mock_partial_failure,
    ):
        response = upload_text(client, chat.id, long_text, token)

        assert response.status_code == 502

        # Verify old vectors are still preserved 100%
        results = VectorRepository.search_similar_chunks(
            user_id=user.id,
            chat_id=chat.id,
            query_vector=[0.1] * 768,
        )
        assert len(results) == 2
