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
    token = create_access_token(user_id=user.id)
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
            "prompt": "     \n   ",
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
            "prompt": "analyze images",
            "image_base64": ["validstring"] * (settings.MAX_IMAGE_COUNT + 1),
            "image_mime": ["image/png"] * (settings.MAX_IMAGE_COUNT + 1),
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_stream_rejects_oversized_single_image(client, test_user_and_chat) -> None:
    _, chat, headers = test_user_and_chat

    response = client.post(
        "/chat/stream",
        json={
            "chat_id": chat.id,
            "prompt": "analyze image",
            "image_base64": ["x" * (settings.MAX_IMAGE_BASE64_CHARS + 1)],
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
            "prompt": "analyze image",
            "image_base64": ["somebase64data"],
            "image_mime": ["image/svg+xml"],
        },
        headers=headers,
    )
    assert response.status_code == 422
