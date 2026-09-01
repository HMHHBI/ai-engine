from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Chat, Message, User
from app.repositories.chat_repo import ChatRepository
from app.services.chat_service import ChatApplicationService


def create_user(
    db_session,
    email: str,
) -> User:
    user = User(
        name="Concurrency Test User",
        email=email,
        password="test-password",
    )

    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    return user


def create_chat(
    db_session,
    user_id: int,
    title: str = "New Chat",
) -> Chat:
    chat = Chat(
        user_id=user_id,
        title=title,
        ai_provider="ollama",
        ai_model="llama3.2",
        embedding_provider="ollama",
    )

    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    return chat


def get_messages(
    db_session,
    chat_id: int,
) -> list[Message]:
    return list(
        db_session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.id.asc())
        ).scalars()
    )


def test_prepare_chat_turn_only_initializes_default_title_once(
    db_session,
):
    user = create_user(
        db_session,
        "title-race@example.com",
    )

    chat = create_chat(
        db_session,
        user.id,
    )

    first = ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="First concurrent request",
        new_title="First concurrent request",
    )

    second = ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="Second concurrent request",
        new_title="Second concurrent request",
    )

    assert first is not None
    assert second is not None

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat.id,
    )

    assert stored_chat is not None
    assert stored_chat.title == "First concurrent request"

    messages = get_messages(
        db_session,
        chat.id,
    )

    assert len(messages) == 2
    assert messages[0].content == "First concurrent request"
    assert messages[1].content == "Second concurrent request"


@pytest.mark.asyncio
async def test_concurrent_chat_turns_preserve_single_title_initializer(
    db_session,
):
    user = create_user(
        db_session,
        "async-title-race@example.com",
    )

    chat = create_chat(
        db_session,
        user.id,
    )

    async def prepare(
        content: str,
    ):
        return await asyncio.to_thread(
            ChatRepository.prepare_chat_turn,
            chat_id=chat.id,
            user_id=user.id,
            content=content,
            new_title=content,
        )

    results = await asyncio.gather(
        prepare("Concurrent A"),
        prepare("Concurrent B"),
    )

    assert all(result is not None for result in results)

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat.id,
    )

    assert stored_chat is not None
    assert stored_chat.title in {
        "Concurrent A",
        "Concurrent B",
    }

    messages = get_messages(
        db_session,
        chat.id,
    )

    assert len(messages) == 2


def test_concurrent_title_initializer_never_restores_new_chat(
    db_session,
):
    user = create_user(
        db_session,
        "title-invariant@example.com",
    )

    chat = create_chat(
        db_session,
        user.id,
    )

    ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="Initial message",
        new_title="Initial message",
    )

    ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="Later message",
        new_title="Later message",
    )

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat.id,
    )

    assert stored_chat is not None
    assert stored_chat.title != "New Chat"
    assert stored_chat.title == "Initial message"


@pytest.mark.asyncio
async def test_chat_application_service_uploads_images_outside_repository():
    repository_message = object()

    with (
        patch(
            "app.services.chat_service.upload_image_to_cloud",
            return_value="https://cloudinary.example/image.png",
        ) as upload_mock,
        patch(
            "app.services.chat_service.ChatRepository.prepare_chat_turn",
            return_value=repository_message,
        ) as repository_mock,
    ):
        result = await ChatApplicationService.prepare_chat_turn(
            chat_id=123,
            user_id=456,
            content="Image message",
            new_title="Image message",
            image_data_list=["base64-data"],
        )

    assert result is repository_message

    upload_mock.assert_called_once_with(
        "base64-data",
        "chat_messages",
    )

    repository_mock.assert_called_once_with(
        chat_id=123,
        user_id=456,
        content="Image message",
        new_title="Image message",
        image_urls=[
            "https://cloudinary.example/image.png",
        ],
    )


@pytest.mark.asyncio
async def test_chat_application_service_preserves_existing_urls():
    repository_message = object()

    with (
        patch(
            "app.services.chat_service.upload_image_to_cloud",
        ) as upload_mock,
        patch(
            "app.services.chat_service.ChatRepository.prepare_chat_turn",
            return_value=repository_message,
        ) as repository_mock,
    ):
        result = await ChatApplicationService.prepare_chat_turn(
            chat_id=123,
            user_id=456,
            content="Existing URL",
            image_data_list=[
                "https://example.com/image.png",
            ],
        )

    assert result is repository_message
    upload_mock.assert_not_called()

    repository_mock.assert_called_once_with(
        chat_id=123,
        user_id=456,
        content="Existing URL",
        new_title=None,
        image_urls=[
            "https://example.com/image.png",
        ],
    )


@pytest.mark.asyncio
async def test_chat_application_service_does_not_call_repository_when_upload_fails():
    with (
        patch(
            "app.services.chat_service.upload_image_to_cloud",
            return_value=None,
        ),
        patch(
            "app.services.chat_service.ChatRepository.prepare_chat_turn",
        ) as repository_mock,
    ):
        with pytest.raises(ValueError):
            await ChatApplicationService.prepare_chat_turn(
                chat_id=123,
                user_id=456,
                content="Upload failure",
                image_data_list=["broken-image"],
            )

    repository_mock.assert_not_called()


def test_settings_expose_explicit_database_pool_configuration():
    settings = Settings(
        DATABASE_URL="postgresql://test:test@localhost/test",
        FRONTEND_URL="http://localhost:3000",
        SECRET_KEY="test-secret",
        CLOUDINARY_NAME="test",
        CLOUDINARY_API_KEY="test",
        CLOUDINARY_API_SECRET="test",
    )

    assert settings.DB_POOL_SIZE > 0
    assert settings.DB_MAX_OVERFLOW >= 0
    assert settings.DB_POOL_TIMEOUT > 0
    assert settings.DB_POOL_RECYCLE > 0
    assert settings.DB_POOL_PRE_PING is True


def test_settings_expose_centralized_ai_timeouts():
    settings = Settings(
        DATABASE_URL="postgresql://test:test@localhost/test",
        FRONTEND_URL="http://localhost:3000",
        SECRET_KEY="test-secret",
        CLOUDINARY_NAME="test",
        CLOUDINARY_API_KEY="test",
        CLOUDINARY_API_SECRET="test",
    )

    assert settings.AI_CONNECT_TIMEOUT > 0
    assert settings.AI_READ_TIMEOUT > 0
    assert settings.AI_WRITE_TIMEOUT > 0
    assert settings.AI_POOL_TIMEOUT > 0
    assert settings.AI_REQUEST_TIMEOUT > 0
    assert settings.AI_STREAM_MAX_SECONDS > 0
