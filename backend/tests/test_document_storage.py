import io
import pytest
from unittest.mock import patch, MagicMock

from app.core.security import create_access_token
from app.db.models import User
from app.storage.local import LocalStorageBackend
from app.storage.keys import build_document_key
from app.repositories.document_repo import DocumentRepository
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository


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

    with patch("app.api.chat.get_storage_backend", return_value=mock_storage):
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
