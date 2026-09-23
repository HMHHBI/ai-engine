from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository


@pytest.fixture()
def test_user_and_chat(db_session):
    user = UserRepository.create(
        db_session,
        name="Input Sec User",
        email="input-sec@example.com",
        password="Password!123",
    )
    chat = ChatRepository.create_chat(user_id=user.id)
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}
    return user, chat, headers


def test_stream_rejects_oversized_prompt(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "a" * (settings.MAX_PROMPT_CHARS + 1),
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_stream_rejects_blank_or_whitespace_prompt(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "   \n\t  ",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_stream_rejects_too_many_images(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "test prompt",
            "image_base64": ["validb64"] * (settings.MAX_IMAGE_COUNT + 1),
            "image_mime": ["image/png"] * (settings.MAX_IMAGE_COUNT + 1),
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_stream_rejects_oversized_individual_image(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "test prompt",
            "image_base64": ["a" * (settings.MAX_IMAGE_BASE64_CHARS + 1)],
            "image_mime": ["image/png"],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_stream_rejects_unsupported_image_mime(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "test prompt",
            "image_base64": ["validb64"],
            "image_mime": ["image/bmp"],
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_ai_request_rejects_missing_mime_when_image_present(
    client, test_user_and_chat
) -> None:
    _, chat, headers = test_user_and_chat
    payload = {
        "chat_id": chat.id,
        "prompt": "Hello",
        "image_base64": ["validbase64string"],
    }
    response = client.post("/chat/stream", json=payload, headers=headers)
    assert response.status_code == 422


def test_ai_request_rejects_missing_image_when_mime_present(
    client, test_user_and_chat
) -> None:
    _, chat, headers = test_user_and_chat
    payload = {
        "chat_id": chat.id,
        "prompt": "Hello",
        "image_mime": ["image/png"],
    }
    response = client.post("/chat/stream", json=payload, headers=headers)
    assert response.status_code == 422


def test_ai_request_rejects_mismatched_image_and_mime_lengths(
    client, test_user_and_chat
) -> None:
    _, chat, headers = test_user_and_chat
    payload = {
        "chat_id": chat.id,
        "prompt": "Hello",
        "image_base64": ["img1", "img2"],
        "image_mime": ["image/png"],
    }
    response = client.post("/chat/stream", json=payload, headers=headers)
    assert response.status_code == 422
