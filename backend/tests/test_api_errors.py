from __future__ import annotations

import time
from io import BytesIO
from unittest.mock import MagicMock, patch
import pytest

from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.services.providers.errors import AIProviderUnavailable
from app.utils.pdf_extractor import PDFExtractionError


@pytest.fixture()
def user_and_chat(db_session):
    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Error Test User",
        email=f"err-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def auth_headers(user):
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_create_chat_db_failure_returns_safe_500(client, user_and_chat):
    user, _ = user_and_chat
    with patch(
        "app.repositories.chat_repo.ChatRepository.create_chat",
        side_effect=Exception("Raw SQL DB connection terminated"),
    ):
        response = client.post("/chat/new", headers=auth_headers(user))
        assert response.status_code == 500
        assert "Raw SQL" not in response.text
        assert response.json()["detail"] == "Unable to create new chat session."


def test_stream_unsupported_model_returns_400(client, user_and_chat):
    user, chat = user_and_chat
    response = client.post(
        "/chat/stream",
        json={"chat_id": chat.id, "prompt": "Hello", "model": "nonexistent-model-xyz"},
        headers=auth_headers(user),
    )
    assert response.status_code == 400
    assert "Unsupported AI model" in response.json()["detail"]


def test_stream_provider_failure_yields_safe_message(client, user_and_chat):
    user, chat = user_and_chat

    async def mock_failing_stream(*args, **kwargs):
        yield "Initial tokens "
        raise AIProviderUnavailable()

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_failing_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Explain RAG"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200
        content = response.text
        assert "Initial tokens" in content
        assert (
            "[The AI provider is temporarily unavailable. Please try again.]" in content
        )


def test_failed_stream_is_not_persisted(client, user_and_chat):
    user, chat = user_and_chat

    async def mock_failing_stream(*args, **kwargs):
        if False:
            yield "never reached"
        raise AIProviderUnavailable()

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_failing_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Test Prompt"},
            headers=auth_headers(user),
        )

    history = ChatRepository.get_history(chat_id=chat.id)
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 0


def test_successful_stream_is_persisted(client, user_and_chat):
    user, chat = user_and_chat

    async def mock_ok_stream(*args, **kwargs):
        yield "Complete "
        yield "AI Response."

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_ok_stream

    with patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Hello"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200

    history = ChatRepository.get_history(chat_id=chat.id)
    ai_messages = [m for m in history if m.role == "ai"]
    assert len(ai_messages) == 1
    assert ai_messages[0].content == "Complete AI Response."


def test_pdf_extraction_domain_error_returns_safe_400(client, user_and_chat):
    user, chat = user_and_chat
    with patch(
        "app.api.chat.extract_text_from_pdf",
        side_effect=PDFExtractionError("Password-protected internal structure"),
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={
                "file": (
                    "test.pdf",
                    BytesIO(b"%PDF-1.4\nsome content"),
                    "application/pdf",
                )
            },
            headers=auth_headers(user),
        )
        assert response.status_code == 400
        assert (
            response.json()["detail"] == "The uploaded document could not be processed."
        )
        assert "Password-protected internal structure" not in response.text


def test_unexpected_parser_crash_returns_safe_500(client, user_and_chat):
    user, chat = user_and_chat
    with patch(
        "app.api.chat.extract_text_from_pdf",
        side_effect=MemoryError("Fatal C++ segmentation fault"),
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={
                "file": (
                    "test.pdf",
                    BytesIO(b"%PDF-1.4\nsome content"),
                    "application/pdf",
                )
            },
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Server error during document ingestion."
        assert "segmentation fault" not in response.text


def test_db_replacement_failure_returns_safe_500(client, user_and_chat):
    user, chat = user_and_chat
    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ), patch(
        "app.repositories.vector_repo.VectorRepository.replace_document_chunks",
        side_effect=Exception("Database lock acquisition timeout"),
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={"file": ("test.txt", BytesIO(b"Valid text content"), "text/plain")},
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Server error during document ingestion."
        assert "Database lock" not in response.text


def test_upgrade_plan_not_found_returns_404(client, user_and_chat):
    user, _ = user_and_chat
    with patch(
        "app.repositories.user_repo.UserRepository.upgrade_to_pro", return_value=None
    ):
        response = client.post(
            "/user/upgrade-plan",
            headers=auth_headers(user),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "User not found."


def test_upgrade_plan_unexpected_exception_returns_500(client, user_and_chat):
    user, _ = user_and_chat
    with patch(
        "app.repositories.user_repo.UserRepository.upgrade_to_pro",
        side_effect=Exception("Stripe webhook sync crash"),
    ):
        response = client.post(
            "/user/upgrade-plan",
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Unable to upgrade plan."
        assert "Stripe" not in response.text


def test_delete_chat_unexpected_exception_returns_500(client, user_and_chat):
    user, chat = user_and_chat
    with patch(
        "app.repositories.chat_repo.ChatRepository.delete_chat",
        side_effect=Exception("Foreign key dead lock"),
    ):
        response = client.delete(f"/chat/{chat.id}", headers=auth_headers(user))
        assert response.status_code == 500
        assert response.json()["detail"] == "Unable to delete chat."
        assert "dead lock" not in response.text
