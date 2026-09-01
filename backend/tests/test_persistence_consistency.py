from __future__ import annotations

from unittest.mock import patch
import pytest
from sqlalchemy import select

from app.db.models import Chat, Message, User
from app.repositories.chat_repo import ChatRepository


def create_user(db_session, email: str) -> User:
    user = User(
        name="Test User",
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
        ai_model="ollama-llama3.2",
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


def test_prepare_chat_turn_atomically_updates_title_and_message(
    db_session,
):
    user = create_user(
        db_session,
        "atomic@example.com",
    )

    chat = create_chat(
        db_session,
        user.id,
        title="New Chat",
    )

    chat_id = chat.id

    message = ChatRepository.prepare_chat_turn(
        chat_id=chat_id,
        user_id=user.id,
        content="Hello production RAG.",
        new_title="Hello production RAG.",
    )

    assert message is not None

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat_id,
    )

    stored_messages = get_messages(
        db_session,
        chat_id,
    )

    assert stored_chat is not None
    assert stored_chat.title == "Hello production RAG."

    assert len(stored_messages) == 1
    assert stored_messages[0].role == "user"
    assert stored_messages[0].content == "Hello production RAG."


def test_prepare_chat_turn_rolls_back_title_when_message_insert_fails(
    db_session,
):
    user = create_user(
        db_session,
        "rollback@example.com",
    )

    chat = create_chat(
        db_session,
        user.id,
        title="New Chat",
    )

    chat_id = chat.id

    # Invalid non-URL image triggers validation failure before committing title
    with pytest.raises(ValueError):
        ChatRepository.prepare_chat_turn(
            chat_id=chat_id,
            user_id=user.id,
            content="This must roll back.",
            new_title="This must roll back.",
            image_urls=["not-a-valid-http-url"],
        )

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat_id,
    )

    stored_messages = get_messages(
        db_session,
        chat_id,
    )

    assert stored_chat is not None
    assert stored_chat.title == "New Chat"
    assert stored_messages == []


def test_prepare_chat_turn_rejects_cross_user_access(
    db_session,
):
    owner = create_user(
        db_session,
        "owner@example.com",
    )

    attacker = create_user(
        db_session,
        "attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    result = ChatRepository.prepare_chat_turn(
        chat_id=chat_id,
        user_id=attacker.id,
        content="Unauthorized message.",
        new_title="Hijacked",
    )

    assert result is None

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat_id,
    )

    stored_messages = get_messages(
        db_session,
        chat_id,
    )

    assert stored_chat is not None
    assert stored_chat.title == "New Chat"
    assert stored_messages == []


def test_update_title_is_user_scoped(
    db_session,
):
    owner = create_user(
        db_session,
        "title-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "title-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
        title="Original",
    )

    chat_id = chat.id

    result = ChatRepository.update_title(
        chat_id=chat_id,
        user_id=attacker.id,
        new_title="Unauthorized",
    )

    assert result is None

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat_id,
    )

    assert stored_chat is not None
    assert stored_chat.title == "Original"


def test_add_message_is_user_scoped(
    db_session,
):
    owner = create_user(
        db_session,
        "message-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "message-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    result = ChatRepository.add_message(
        chat_id=chat_id,
        user_id=attacker.id,
        role="user",
        content="Unauthorized message.",
    )

    assert result is None

    assert (
        get_messages(
            db_session,
            chat_id,
        )
        == []
    )


def test_get_history_is_user_scoped(
    db_session,
):
    owner = create_user(
        db_session,
        "history-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "history-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    owner_message = ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="Private message.",
    )

    assert owner_message is not None

    owner_history = ChatRepository.get_history(
        chat_id=chat_id,
        user_id=owner.id,
        limit=50,
    )

    attacker_history = ChatRepository.get_history(
        chat_id=chat_id,
        user_id=attacker.id,
        limit=50,
    )

    assert len(owner_history) == 1
    assert owner_history[0].content == "Private message."

    assert attacker_history == []


def test_update_pdf_context_is_user_scoped(
    db_session,
):
    owner = create_user(
        db_session,
        "pdf-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "pdf-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    result = ChatRepository.update_pdf_context(
        chat_id=chat_id,
        user_id=attacker.id,
        text="Unauthorized document.",
    )

    assert result is None

    db_session.expire_all()

    stored_chat = db_session.get(
        Chat,
        chat_id,
    )

    assert stored_chat is not None
    assert stored_chat.pdf_context is None


def test_delete_messages_after_is_user_scoped(
    db_session,
):
    owner = create_user(
        db_session,
        "cleanup-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "cleanup-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="First",
    )

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="Second",
    )

    result = ChatRepository.delete_messages_after(
        chat_id=chat_id,
        user_id=attacker.id,
        after_index=0,
    )

    assert result is False

    messages = get_messages(
        db_session,
        chat_id,
    )

    assert len(messages) == 2


def test_owner_can_delete_messages_after(
    db_session,
):
    owner = create_user(
        db_session,
        "cleanup-owner-2@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="First",
    )

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="Second",
    )

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="Third",
    )

    result = ChatRepository.delete_messages_after(
        chat_id=chat_id,
        user_id=owner.id,
        after_index=1,
    )

    assert result is True

    messages = get_messages(
        db_session,
        chat_id,
    )

    assert len(messages) == 1
    assert messages[0].content == "First"


def test_chat_deletion_cascades_messages(
    db_session,
):
    owner = create_user(
        db_session,
        "cascade@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="user",
        content="Will be deleted.",
    )

    ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="ai",
        content="Also deleted.",
    )

    assert len(get_messages(db_session, chat_id)) == 2

    result = ChatRepository.delete_chat(
        chat_id=chat_id,
        user_id=owner.id,
    )

    assert result is True

    db_session.expire_all()

    assert db_session.get(Chat, chat_id) is None
    assert get_messages(db_session, chat_id) == []


def test_cross_user_delete_chat_is_rejected(
    db_session,
):
    owner = create_user(
        db_session,
        "delete-owner@example.com",
    )

    attacker = create_user(
        db_session,
        "delete-attacker@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    result = ChatRepository.delete_chat(
        chat_id=chat_id,
        user_id=attacker.id,
    )

    assert result is False

    db_session.expire_all()

    assert (
        db_session.get(
            Chat,
            chat_id,
        )
        is not None
    )


def test_ai_response_persistence_succeeds_for_owner(
    db_session,
):
    owner = create_user(
        db_session,
        "ai-owner@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    message = ChatRepository.add_message(
        chat_id=chat_id,
        user_id=owner.id,
        role="ai",
        content="Persisted AI response.",
    )

    assert message is not None

    messages = get_messages(
        db_session,
        chat_id,
    )

    assert len(messages) == 1
    assert messages[0].role == "ai"
    assert messages[0].content == "Persisted AI response."


def test_ai_response_persistence_failure_rolls_back(
    db_session,
):
    owner = create_user(
        db_session,
        "ai-failure@example.com",
    )

    chat = create_chat(
        db_session,
        owner.id,
    )

    chat_id = chat.id

    with patch(
        "app.repositories.chat_repo.session_scope",
        side_effect=RuntimeError("database unavailable"),
    ):
        with pytest.raises(RuntimeError):
            ChatRepository.add_message(
                chat_id=chat_id,
                user_id=owner.id,
                role="ai",
                content="Must not persist.",
            )

    assert (
        get_messages(
            db_session,
            chat_id,
        )
        == []
    )
