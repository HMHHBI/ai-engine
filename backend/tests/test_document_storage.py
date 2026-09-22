import io
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

from app.core.security import create_access_token
from app.db.models import User, DocumentChunk
from app.storage.local import LocalStorageBackend
from app.storage.keys import build_document_key
from app.repositories.document_repo import DocumentRepository
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository
from app.utils.pdf_extractor import PDFPage


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def test_local_storage_lifecycle(tmp_path):
    storage = LocalStorageBackend(root=tmp_path)
    key = build_document_key(user_id=1)
    test_data = b"%PDF-1.4 test binary stream data"

    # 1. Save
    saved_key = storage.save(key, io.BytesIO(test_data), content_type="application/pdf")
    assert saved_key == key
    assert storage.exists(key) is True

    # 2. Read
    stream = storage.get_stream(key)
    assert stream.read() == test_data

    # 3. Delete
    storage.delete(key)
    assert storage.exists(key) is False


def test_path_traversal_prevention(tmp_path):
    storage = LocalStorageBackend(root=tmp_path)

    with pytest.raises(ValueError, match="escapes the storage root"):
        storage.save(
            "../malicious.pdf", io.BytesIO(b"data"), content_type="application/pdf"
        )


def test_build_document_key_validation():
    with pytest.raises(ValueError):
        build_document_key(user_id=0)

    key = build_document_key(user_id=42)
    assert key.startswith("raw_pdfs/42/")
    assert key.endswith(".pdf")


def test_storage_failure_before_db_creation(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 1",
        email="comp-user1@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")

    mock_storage = MagicMock()
    mock_storage.save.side_effect = IOError("Disk write failed")

    with patch("app.api.chat.get_storage_backend", return_value=mock_storage), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new_callable=AsyncMock,
        return_value=[0.1] * 768,
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={
                "file": (
                    "test.txt",
                    b"Valid text file content for storage test",
                    "text/plain",
                )
            },
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Document storage failed."

    docs = DocumentRepository.list_for_chat(chat_id=chat.id, user_id=user.id)
    assert len(docs) == 0


def test_db_creation_failure_cleans_up_storage(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 2",
        email="comp-user2@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")

    mock_storage = MagicMock()

    with patch("app.api.chat.get_storage_backend", return_value=mock_storage), patch(
        "app.repositories.document_repo.DocumentRepository.create", return_value=None
    ), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new_callable=AsyncMock,
        return_value=[0.1] * 768,
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={
                "file": (
                    "test.txt",
                    b"Valid text file content for storage test",
                    "text/plain",
                )
            },
            headers=auth_headers(user),
        )
        assert response.status_code == 404
        assert mock_storage.delete.called


def test_vector_indexing_failure_cleans_storage_and_marks_failed(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 3",
        email="comp-user3@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")

    mock_storage = MagicMock()

    with patch("app.api.chat.get_storage_backend", return_value=mock_storage), patch(
        "app.repositories.vector_repo.VectorRepository.replace_document_chunks",
        side_effect=Exception("DB dead"),
    ), patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new_callable=AsyncMock,
        return_value=[0.1] * 768,
    ):
        response = client.post(
            f"/chat/upload-pdf/{chat.id}",
            files={
                "file": (
                    "test.txt",
                    b"Valid text file content for storage test",
                    "text/plain",
                )
            },
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert mock_storage.delete.called

    docs = DocumentRepository.list_for_chat(chat_id=chat.id, user_id=user.id)
    assert len(docs) == 1
    assert docs[0].status == "failed"


def test_delete_failure_in_storage_preserves_db_document(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 4",
        email="comp-user4@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="preserve.pdf",
        mime_type="application/pdf",
        file_size=100,
        storage_key="raw_pdfs/4/preserve.pdf",
    )

    mock_storage = MagicMock()
    mock_storage.delete.side_effect = IOError("Storage down")

    with patch("app.api.documents.get_storage_backend", return_value=mock_storage):
        response = client.delete(
            f"/documents/{doc.id}",
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete document from storage."

    persisted = DocumentRepository.get_owned_document(
        document_id=doc.id, user_id=user.id
    )
    assert persisted is not None


from types import SimpleNamespace


def test_successful_deletion_cascades_to_chunks(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 5",
        email="comp-user5@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="cascade.pdf",
        mime_type="application/pdf",
        file_size=100,
        storage_key="raw_pdfs/5/cascade.pdf",
    )

    # Insert vector chunks with proper chunk attributes
    chunk_item = SimpleNamespace(
        chunk_index=0,
        page_number=1,
        text="Sample text chunk for cascade test",
    )
    chunks = [(chunk_item, [0.1] * 768)]
    VectorRepository.replace_document_chunks(
        user_id=user.id,
        document_id=doc.id,
        chunks_with_embeddings=chunks,
    )

    # Verify chunks exist in DB
    existing_chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .all()
    )
    assert len(existing_chunks) > 0

    mock_storage = MagicMock()
    with patch("app.api.documents.get_storage_backend", return_value=mock_storage):
        response = client.delete(
            f"/documents/{doc.id}",
            headers=auth_headers(user),
        )
        assert response.status_code == 204
        assert mock_storage.delete.called

    # Verify document and chunks are completely gone
    persisted = DocumentRepository.get_owned_document(
        document_id=doc.id, user_id=user.id
    )
    assert persisted is None

    remaining_chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .all()
    )
    assert len(remaining_chunks) == 0


def test_db_deletion_failure_preserves_document(client, db_session):
    user = UserRepository.create(
        db_session,
        name="Comp User 6",
        email="comp-user6@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id, title="Comp Chat")
    doc = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="db_fail.pdf",
        mime_type="application/pdf",
        file_size=100,
        storage_key="raw_pdfs/6/db_fail.pdf",
    )

    mock_storage = MagicMock()
    with patch(
        "app.api.documents.get_storage_backend", return_value=mock_storage
    ), patch(
        "app.repositories.document_repo.DocumentRepository.delete",
        side_effect=Exception("DB deadlock"),
    ):
        response = client.delete(
            f"/documents/{doc.id}",
            headers=auth_headers(user),
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to delete document from database."

    persisted = DocumentRepository.get_owned_document(
        document_id=doc.id, user_id=user.id
    )
    assert persisted is not None
