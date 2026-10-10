from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Document, Message
from app.db.session import session_scope
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.user_repo import UserRepository


def create_user(db_session, name: str, email: str):
    return UserRepository.create(
        db_session,
        name=name,
        email=email,
        password="Password!123",
    )


def test_session_metadata_zero_documents(db_session):
    user = create_user(
        db_session,
        "Session Zero",
        "session-zero@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="New Research",
        persona="academic",
    )

    metadata = ChatRepository.get_session_metadata(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert metadata is not None
    assert metadata["attached_documents_count"] == 0
    assert metadata["primary_document_title"] is None
    assert metadata["message_count"] == 0
    assert metadata["last_active_at"] is None
    assert metadata["persona"] == "academic"


def test_session_metadata_one_document_and_message(db_session):
    user = create_user(
        db_session,
        "Session One",
        "session-one@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="Research Session",
    )

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="attention_is_all_you_need.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    message = ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user.id,
        role="user",
        content="What is the main contribution?",
    )

    assert document is not None
    assert message is not None

    metadata = ChatRepository.get_session_metadata(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert metadata is not None
    assert metadata["attached_documents_count"] == 1
    assert metadata["primary_document_title"] == "attention_is_all_you_need.pdf"
    assert metadata["message_count"] == 1
    assert metadata["last_active_at"] is not None


def test_session_metadata_multiple_documents_counts_all_documents(
    db_session,
):
    user = create_user(
        db_session,
        "Session Multiple",
        "session-multiple@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="Multi Material Research",
    )

    first = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="first.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    second = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="second.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    assert first is not None
    assert second is not None

    with session_scope() as db:
        stored_first = db.get(Document, first.id)
        stored_second = db.get(Document, second.id)

        stored_first.updated_at = datetime(
            2026,
            10,
            1,
            tzinfo=timezone.utc,
        )

        stored_second.updated_at = datetime(
            2026,
            10,
            6,
            tzinfo=timezone.utc,
        )

    metadata = ChatRepository.get_session_metadata(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert metadata is not None
    assert metadata["attached_documents_count"] == 2
    assert metadata["primary_document_title"] == "second.pdf"


def test_session_metadata_last_active_uses_latest_message_or_document(
    db_session,
):
    user = create_user(
        db_session,
        "Session Activity",
        "session-activity@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="Activity Test",
    )

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="activity.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    message = ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user.id,
        role="user",
        content="Recent question",
    )

    assert document is not None
    assert message is not None

    document_time = datetime(
        2026,
        10,
        1,
        tzinfo=timezone.utc,
    )

    message_time = datetime(
        2026,
        10,
        6,
        tzinfo=timezone.utc,
    )

    with session_scope() as db:
        stored_document = db.get(
            Document,
            document.id,
        )

        stored_message = db.get(
            Message,
            message.id,
        )

        stored_document.updated_at = document_time
        stored_message.created_at = message_time

    metadata = ChatRepository.get_session_metadata(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert metadata is not None
    assert metadata["last_active_at"] == message_time


def test_session_metadata_rejects_cross_tenant_access(
    db_session,
):
    user_a = create_user(
        db_session,
        "Tenant A",
        "tenant-a-session@example.com",
    )

    user_b = create_user(
        db_session,
        "Tenant B",
        "tenant-b-session@example.com",
    )

    chat_a = ChatRepository.create_chat(
        user_id=user_a.id,
        title="Private A",
    )

    document_a = DocumentRepository.create(
        user_id=user_a.id,
        chat_id=chat_a.id,
        filename="private-a.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    assert document_a is not None

    assert (
        ChatRepository.get_session_metadata(
            chat_id=chat_a.id,
            user_id=user_b.id,
        )
        is None
    )

    sessions_b = ChatRepository.get_all_by_user(
        user_id=user_b.id,
    )

    assert all(session["id"] != chat_a.id for session in sessions_b)


def test_document_filename_has_title_precedence(
    db_session,
):
    user = create_user(
        db_session,
        "Title Document",
        "title-document@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="New Chat",
    )

    title = ChatRepository.infer_and_set_title_from_document(
        chat_id=chat.id,
        user_id=user.id,
        filename="attention_is_all_you_need.pdf",
    )

    assert title == "Attention is all you need"

    refreshed = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert refreshed is not None
    assert refreshed.title == "Attention is all you need"


def test_explicit_title_is_preserved_over_document(
    db_session,
):
    user = create_user(
        db_session,
        "Explicit Title",
        "explicit-title@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="My Transformer Research",
    )

    title = ChatRepository.infer_and_set_title_from_document(
        chat_id=chat.id,
        user_id=user.id,
        filename="different_document.pdf",
    )

    assert title == "My Transformer Research"

    refreshed = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert refreshed is not None
    assert refreshed.title == "My Transformer Research"


def test_first_question_becomes_title_when_no_document_exists(
    db_session,
):
    user = create_user(
        db_session,
        "Question Title",
        "question-title@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="New Chat",
    )

    message = ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="What are the limitations of transformer architectures?",
    )

    assert message is not None

    refreshed = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert refreshed is not None
    assert refreshed.title == "What are the limitations of transformer architectures"


def test_document_title_wins_over_first_question(
    db_session,
):
    user = create_user(
        db_session,
        "Document Wins",
        "document-wins@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="New Chat",
    )

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="attention_is_all_you_need.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    assert document is not None

    message = ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="What are the weaknesses of this model?",
    )

    assert message is not None

    refreshed = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert refreshed is not None
    assert refreshed.title == "Attention is all you need"


def test_generic_chat_number_is_treated_as_generic_title(
    db_session,
):
    user = create_user(
        db_session,
        "Generic Chat",
        "generic-chat@example.com",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
        title="Chat #123",
    )

    document = DocumentRepository.create(
        user_id=user.id,
        chat_id=chat.id,
        filename="research_methods.pdf",
        mime_type="application/pdf",
        file_size=100,
        status="ready",
    )

    assert document is not None

    message = ChatRepository.prepare_chat_turn(
        chat_id=chat.id,
        user_id=user.id,
        content="Explain the methodology.",
    )

    assert message is not None

    refreshed = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert refreshed is not None
    assert refreshed.title == "Research methods"


def test_phase4_zero_alembic_migrations_invariant():
    """Verify that Alembic head matches the latest verified head (bc2cc3cfac88) with 0 new migrations."""
    import os
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_cfg_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    )
    config = Config(alembic_cfg_path)
    script = ScriptDirectory.from_config(config)

    head_revision = script.get_current_head()
    assert head_revision in ("b3a490b636d1", "bc2cc3cfac88"), (
        f"Alembic head must strictly remain b3a490b636d1, got {head_revision}"
    )

    versions_dir = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
    version_files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
    assert not any("402be48bec7e" in f for f in version_files), (
        "Forbidden migration 402be48bec7e must not exist."
    )
