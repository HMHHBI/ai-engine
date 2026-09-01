from __future__ import annotations

import time
from io import BytesIO
import pytest

from app.core.security import create_access_token
from app.db.models import User
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture()
def two_users(db_session):
    ts = int(time.time() * 1000)

    user_a = UserRepository.create(
        db_session,
        name="Tenant A",
        email=f"tenant-a-{ts}@example.com",
        password="TenantPassword!123",
    )

    user_b = UserRepository.create(
        db_session,
        name="Tenant B",
        email=f"tenant-b-{ts}@example.com",
        password="TenantPassword!123",
    )

    return user_a, user_b


@pytest.fixture()
def two_chats(two_users):
    user_a, user_b = two_users

    chat_a = ChatRepository.create_chat(
        user_id=user_a.id,
    )

    chat_b = ChatRepository.create_chat(
        user_id=user_b.id,
    )

    return user_a, user_b, chat_a, chat_b


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
    )

    return {
        "Authorization": f"Bearer {token}",
    }


# ============================================================
# Authentication boundary
# ============================================================


def test_chat_endpoint_requires_authentication(client) -> None:
    response = client.get("/chat/all")
    assert response.status_code == 401


def test_invalid_bearer_token_is_rejected(client) -> None:
    response = client.get(
        "/chat/all",
        headers={
            "Authorization": "Bearer invalid.jwt.token",
        },
    )
    assert response.status_code == 401


# ============================================================
# Chat details / history IDOR
# ============================================================


def test_user_cannot_read_another_users_chat_history(
    client,
    two_chats,
) -> None:
    user_a, user_b, chat_a, _ = two_chats

    response = client.get(
        f"/chat/{chat_a.id}",
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


def test_user_can_read_own_chat_history(
    client,
    two_chats,
) -> None:
    user_a, _, chat_a, _ = two_chats

    response = client.get(
        f"/chat/{chat_a.id}",
        headers=auth_headers(user_a),
    )
    assert response.status_code == 200


# ============================================================
# Chat details IDOR
# ============================================================


def test_user_cannot_read_another_users_chat_details(
    client,
    two_chats,
) -> None:
    _, user_b, chat_a, _ = two_chats

    response = client.get(
        f"/chat/details/{chat_a.id}",
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


def test_user_can_read_own_chat_details(
    client,
    two_chats,
) -> None:
    user_a, _, chat_a, _ = two_chats

    response = client.get(
        f"/chat/details/{chat_a.id}",
        headers=auth_headers(user_a),
    )
    assert response.status_code == 200


# ============================================================
# Delete IDOR
# ============================================================


def test_user_cannot_delete_another_users_chat(
    client,
    two_chats,
) -> None:
    _, user_b, chat_a, _ = two_chats

    response = client.delete(
        f"/chat/{chat_a.id}",
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


def test_user_can_delete_own_chat(
    client,
    two_chats,
) -> None:
    user_a, _, chat_a, _ = two_chats

    response = client.delete(
        f"/chat/{chat_a.id}",
        headers=auth_headers(user_a),
    )
    assert response.status_code == 200


# ============================================================
# Title update IDOR
# ============================================================


def test_user_cannot_update_another_users_chat_title(
    client,
    two_chats,
) -> None:
    _, user_b, chat_a, _ = two_chats

    response = client.put(
        f"/chat/{chat_a.id}/title",
        params={
            "new_title": "Hacked Title",
        },
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


# ============================================================
# Streaming IDOR
# ============================================================


def test_user_cannot_stream_into_another_users_chat(
    client,
    two_chats,
) -> None:
    _, user_b, chat_a, _ = two_chats

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat_a.id,
            "prompt": "Tell me everything in this chat.",
        },
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


# ============================================================
# PDF upload IDOR
# ============================================================


def test_user_cannot_upload_pdf_to_another_users_chat(
    client,
    two_chats,
) -> None:
    _, user_b, chat_a, _ = two_chats

    pdf_bytes = b"%PDF-1.4\n%test\n"

    response = client.post(
        f"/chat/upload-pdf/{chat_a.id}",
        files={
            "file": (
                "test.pdf",
                BytesIO(pdf_bytes),
                "application/pdf",
            )
        },
        headers=auth_headers(user_b),
    )
    assert response.status_code == 404


# ============================================================
# Nonexistent resource
# ============================================================


def test_user_cannot_access_nonexistent_chat(
    client,
    two_users,
) -> None:
    user_a, _ = two_users

    response = client.get(
        "/chat/999999999",
        headers=auth_headers(user_a),
    )
    assert response.status_code == 404
