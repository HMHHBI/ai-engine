import io
import json
from unittest.mock import patch, MagicMock
import pytest

from app.core.security import create_access_token
from app.db.models import User, DocumentChunk
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository
from app.storage.keys import build_document_key
from app.storage.factory import get_storage_backend
from types import SimpleNamespace


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# A. File Endpoint - Authorization & Failure Contract
# =============================================================================


def test_01_owner_can_retrieve_file(client, db_session):
    user = UserRepository.create(
        db_session,
        name="M2 Owner",
        email="m2-owner@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="M2 Chat")
    storage = get_storage_backend()

    key = build_document_key(user_id=user.id)
    pdf_bytes = b"%PDF-1.4 sample stream bytes"
    storage.save(key, io.BytesIO(pdf_bytes), content_type="application/pdf")

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="report.pdf",
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
        storage_key=key,
    )

    response = client.get(f"/documents/{doc.id}/file", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="report.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == pdf_bytes


def test_02_cross_user_idor_returns_404_without_calling_storage(client, db_session):
    user_a = UserRepository.create(
        db_session, name="User A", email="usera@example.com", password="Password!123"
    )
    user_b = UserRepository.create(
        db_session, name="User B", email="userb@example.com", password="Password!123"
    )

    chat_b = ChatRepository.create_chat(user_id=user_b.id, title="Chat B")
    doc_b = DocumentRepository.create(
        user_id=user_b.id,
        chat_id=chat_b.id,
        filename="b_private.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/b/private.pdf",
    )

    with patch("app.api.documents.get_storage_backend") as mock_get_storage:
        response = client.get(
            f"/documents/{doc_b.id}/file", headers=auth_headers(user_a)
        )
        assert response.status_code == 404
        assert not mock_get_storage.called


def test_03_unauthenticated_request_rejected(client, db_session):
    response = client.get("/documents/1/file")
    assert response.status_code in {401, 403}


def test_04_storage_key_none_returns_404(client, db_session):
    user = UserRepository.create(
        db_session,
        name="M2 Null Key",
        email="m2-null@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Null")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="legacy.pdf",
        mime_type="application/pdf",
        storage_key=None,
    )

    with patch("app.api.documents.get_storage_backend") as mock_get_storage:
        response = client.get(f"/documents/{doc.id}/file", headers=auth_headers(user))
        assert response.status_code == 404
        assert not mock_get_storage.called


def test_05_missing_storage_object_returns_404(client, db_session):
    user = UserRepository.create(
        db_session,
        name="M2 Missing Obj",
        email="m2-missing@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Missing")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="missing.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/missing/file.pdf",
    )

    mock_storage = MagicMock()
    mock_storage.get_stream.side_effect = FileNotFoundError("Missing in driver")

    with patch("app.api.documents.get_storage_backend", return_value=mock_storage):
        response = client.get(f"/documents/{doc.id}/file", headers=auth_headers(user))
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."


def test_06_unexpected_storage_error_returns_500_sanitized(client, db_session):
    user = UserRepository.create(
        db_session,
        name="M2 Err User",
        email="m2-err@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Err")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="err.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/err/file.pdf",
    )

    mock_storage = MagicMock()
    mock_storage.get_stream.side_effect = RuntimeError(
        "AWS/R2 internal bucket connection error: secret_key_123"
    )

    with patch("app.api.documents.get_storage_backend", return_value=mock_storage):
        response = client.get(f"/documents/{doc.id}/file", headers=auth_headers(user))
        assert response.status_code == 500
        data = response.json()
        assert "secret_key_123" not in json.dumps(data)
        assert "bucket" not in json.dumps(data).lower()
        assert data["detail"] == "Failed to retrieve document file."


# =============================================================================
# B. Provenance & Citations Contract
# =============================================================================


def test_07_retrieval_preserves_document_id(db_session):
    user = UserRepository.create(
        db_session,
        name="User Ret",
        email="user-ret@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Ret")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="ret.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/ret/file.pdf",
    )

    chunk_item = SimpleNamespace(
        chunk_index=0, page_number=3, text="Information on deep learning models"
    )
    VectorRepository.replace_document_chunks(
        user_id=user.id,
        document_id=doc.id,
        chunks_with_embeddings=[(chunk_item, [0.05] * 768)],
    )

    chunks = VectorRepository.search_similar_chunks(
        user_id=user.id,
        document_id=doc.id,
        query_vector=[0.05] * 768,
        top_k=1,
    )
    assert len(chunks) == 1
    assert chunks[0]["document_id"] == doc.id


def test_08_sse_preserves_document_id(client, db_session):
    user = UserRepository.create(
        db_session,
        name="User SSE",
        email="user-sse@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat SSE")
    ChatRepository.update_pdf_context(
        chat_id=chat.id, user_id=user.id, text="Indexed File: test.pdf"
    )

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="sse.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/sse/file.pdf",
    )
    DocumentRepository.update_status(
        document_id=doc.id, user_id=user.id, status="ready"
    )

    mock_chunks = [
        {
            "id": 99,
            "document_id": doc.id,
            "content": "Grounding text for SSE test",
            "page_number": 4,
            "chunk_index": 2,
            "distance": 0.12,
        }
    ]

    async def mock_stream(*args, **kwargs):
        yield "Hello "
        yield "world"

    mock_provider = MagicMock()
    mock_provider.generate_stream.side_effect = mock_stream

    with patch(
        "app.repositories.vector_repo.VectorRepository.search_hybrid_chunks",
        return_value=mock_chunks,
    ), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ), patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):

        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Tell me something"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200

        events = response.text.split("\n\n")
        sources_event = next((e for e in events if "event: sources" in e), None)
        assert sources_event is not None

        data_line = next(
            line for line in sources_event.split("\n") if line.startswith("data:")
        )
        payload = json.loads(data_line.replace("data:", "").strip())
        assert payload["sources"][0]["document_id"] == doc.id
        assert payload["sources"][0]["page_number"] == 4


def test_09_message_persistence_preserves_document_id(client, db_session):
    user = UserRepository.create(
        db_session,
        name="User Persist",
        email="user-p@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Persist")
    ChatRepository.update_pdf_context(
        chat_id=chat.id, user_id=user.id, text="Indexed File: test.pdf"
    )

    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="p.pdf",
        mime_type="application/pdf",
        storage_key="raw_pdfs/p/file.pdf",
    )
    DocumentRepository.update_status(
        document_id=doc.id, user_id=user.id, status="ready"
    )

    mock_chunks = [
        {
            "id": 105,
            "document_id": doc.id,
            "content": "Grounding text for persistence test",
            "page_number": 8,
            "chunk_index": 5,
            "distance": 0.22,
        }
    ]

    async def mock_stream(*args, **kwargs):
        yield "Answer token"

    mock_provider = MagicMock()
    mock_provider.generate_stream.side_effect = mock_stream

    with patch(
        "app.repositories.vector_repo.VectorRepository.search_hybrid_chunks",
        return_value=mock_chunks,
    ), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ), patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):

        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Question"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
    ai_msg = next(m for m in history if m.role == "ai")
    assert ai_msg.sources is not None
    assert ai_msg.sources[0]["document_id"] == doc.id
    assert ai_msg.sources[0]["page_number"] == 8


def test_10_legacy_null_document_id_does_not_crash(client, db_session):
    user = UserRepository.create(
        db_session,
        name="User Legacy",
        email="user-legacy@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Chat Legacy")
    ChatRepository.update_pdf_context(
        chat_id=chat.id, user_id=user.id, text="Indexed File: test.pdf"
    )

    # Source without document_id (legacy)
    mock_chunks = [
        {
            "id": 200,
            "document_id": None,
            "content": "Legacy passage text",
            "page_number": 1,
            "chunk_index": 0,
            "distance": 0.15,
        }
    ]

    async def mock_stream(*args, **kwargs):
        yield "Legacy response"

    mock_provider = MagicMock()
    mock_provider.generate_stream.side_effect = mock_stream

    with patch(
        "app.repositories.vector_repo.VectorRepository.search_hybrid_chunks",
        return_value=mock_chunks,
    ), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        return_value=[0.1] * 768,
    ), patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider",
        return_value=mock_provider,
    ):

        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "Legacy query"},
            headers=auth_headers(user),
        )
        assert response.status_code == 200

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
    ai_msg = next(m for m in history if m.role == "ai")
    assert ai_msg.sources is not None
    assert ai_msg.sources[0]["document_id"] is None
