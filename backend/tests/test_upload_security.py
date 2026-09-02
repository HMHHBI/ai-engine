from __future__ import annotations

from io import BytesIO
import pytest

from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture()
def user_and_chat(db_session):
    import time

    ts = int(time.time() * 1000)
    user = UserRepository.create(
        db_session,
        name="Upload User",
        email=f"upload-user-{ts}@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    return user, chat


def upload(
    client,
    chat_id: int,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    headers: dict[str, str],
):
    return client.post(
        f"/chat/upload-pdf/{chat_id}",
        files={"file": (filename, BytesIO(content), content_type)},
        headers=headers,
    )


def test_rejects_oversized_upload(client, user_and_chat, monkeypatch):
    user, chat = user_and_chat
    monkeypatch.setattr("app.core.config.settings.MAX_UPLOAD_SIZE_BYTES", 10)

    response = upload(
        client,
        chat.id,
        filename="test.txt",
        content=b"this is definitely larger than 10 bytes",
        content_type="text/plain",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 413


def test_rejects_pdf_with_fake_signature(client, user_and_chat):
    user, chat = user_and_chat
    response = upload(
        client,
        chat.id,
        filename="malicious.pdf",
        content=b"this is not a pdf file content",
        content_type="application/pdf",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 415


def test_rejects_mismatched_mime_type(client, user_and_chat):
    user, chat = user_and_chat
    response = upload(
        client,
        chat.id,
        filename="document.pdf",
        content=b"%PDF-1.7\ninvalid test",
        content_type="text/plain",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 415


def test_rejects_unsupported_extension(client, user_and_chat):
    user, chat = user_and_chat
    response = upload(
        client,
        chat.id,
        filename="payload.exe",
        content=b"MZ\x90\x00",
        content_type="application/octet-stream",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 415


def test_rejects_empty_file(client, user_and_chat):
    user, chat = user_and_chat
    response = upload(
        client,
        chat.id,
        filename="empty.txt",
        content=b"",
        content_type="text/plain",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 400


def test_rejects_invalid_utf8(client, user_and_chat):
    user, chat = user_and_chat
    response = upload(
        client,
        chat.id,
        filename="invalid.txt",
        content=b"\xff\xfe\xfd",
        content_type="text/plain",
        headers={"Authorization": f"Bearer {create_access_token(user.id)}"},
    )
    assert response.status_code == 415
