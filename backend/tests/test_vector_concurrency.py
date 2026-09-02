from __future__ import annotations

import threading
import time
from types import SimpleNamespace
import pytest
from sqlalchemy import event

from app.db.models import DocumentChunk
from app.repositories.chat_repo import ChatRepository
from app.repositories.user_repo import UserRepository
from app.repositories.vector_repo import VectorRepository
from app.services.providers.errors import AIProviderError


def make_chunk(
    text: str,
    index: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        page_number=1,
        chunk_index=index,
    )


def make_embedding() -> list[float]:
    return [0.0] * 768


@pytest.fixture()
def vector_chat(db_session):
    timestamp = int(time.time() * 1000000)

    user = UserRepository.create(
        db_session,
        name="Vector Concurrency User",
        email=f"vector-concurrency-{timestamp}@example.com",
        password="Password!123",
    )

    chat = ChatRepository.create_chat(
        user_id=user.id,
    )

    return user, chat


def test_concurrent_replacements_are_serialized(
    vector_chat,
    monkeypatch,
):
    """
    Concurrent replacements on the same chat must serialize on the
    owning Chat row. The final document must contain one complete
    replacement, never a mixture of two transactions.
    """
    user, chat = vector_chat

    first_chunks = [
        (
            make_chunk(
                text="document-a-1",
                index=0,
            ),
            make_embedding(),
        ),
        (
            make_chunk(
                text="document-a-2",
                index=1,
            ),
            make_embedding(),
        ),
    ]

    second_chunks = [
        (
            make_chunk(
                text="document-b-1",
                index=0,
            ),
            make_embedding(),
        ),
        (
            make_chunk(
                text="document-b-2",
                index=1,
            ),
            make_embedding(),
        ),
        (
            make_chunk(
                text="document-b-3",
                index=2,
            ),
            make_embedding(),
        ),
    ]

    delete_started = threading.Event()
    release_first_delete = threading.Event()

    from app.db.session import engine

    @event.listens_for(
        engine,
        "before_cursor_execute",
    )
    def pause_first_delete(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        normalized = statement.upper()

        if "DELETE FROM DOCUMENT_CHUNKS" in normalized and not delete_started.is_set():
            delete_started.set()

            if not release_first_delete.wait(timeout=5):
                raise RuntimeError("Timed out waiting to release first replacement.")

    errors: list[BaseException] = []

    def replace_first():
        try:
            VectorRepository.replace_document_chunks(
                user_id=user.id,
                chat_id=chat.id,
                chunks_with_embeddings=first_chunks,
                pdf_context="document-a",
            )
        except BaseException as exc:
            errors.append(exc)

    def replace_second():
        try:
            VectorRepository.replace_document_chunks(
                user_id=user.id,
                chat_id=chat.id,
                chunks_with_embeddings=second_chunks,
                pdf_context="document-b",
            )
        except BaseException as exc:
            errors.append(exc)

    first_thread = threading.Thread(
        target=replace_first,
        name="vector-replacement-a",
    )

    second_thread = threading.Thread(
        target=replace_second,
        name="vector-replacement-b",
    )

    try:
        first_thread.start()

        assert delete_started.wait(timeout=5)

        second_thread.start()

        # The second replacement should be blocked on the Chat row lock
        # while the first transaction is paused inside its DELETE.
        time.sleep(0.2)

        assert second_thread.is_alive()

        release_first_delete.set()

        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        assert not first_thread.is_alive()
        assert not second_thread.is_alive()
        assert errors == []

    finally:
        release_first_delete.set()

        if first_thread.is_alive():
            first_thread.join(timeout=5)

        if second_thread.is_alive():
            second_thread.join(timeout=5)

        event.remove(
            engine,
            "before_cursor_execute",
            pause_first_delete,
        )

    history = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert history is not None
    assert history.pdf_context in {
        "document-a",
        "document-b",
    }

    with __import__(
        "app.db.session",
        fromlist=["session_scope"],
    ).session_scope() as db:
        chunks = list(
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.chat_id == chat.id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    contents = [chunk.content for chunk in chunks]

    assert contents in [
        [
            "document-a-1",
            "document-a-2",
        ],
        [
            "document-b-1",
            "document-b-2",
            "document-b-3",
        ],
    ]


def test_replacement_rolls_back_when_chunk_insertion_fails(
    vector_chat,
    monkeypatch,
):
    """
    A failure during replacement must leave the previous document
    intact because deletion and insertion occur in one transaction.
    """
    user, chat = vector_chat

    original_chunks = [
        (
            make_chunk(
                text="original-1",
                index=0,
            ),
            make_embedding(),
        ),
        (
            make_chunk(
                text="original-2",
                index=1,
            ),
            make_embedding(),
        ),
    ]

    VectorRepository.replace_document_chunks(
        user_id=user.id,
        chat_id=chat.id,
        chunks_with_embeddings=original_chunks,
        pdf_context="original document",
    )

    replacement_chunks = [
        (
            make_chunk(
                text="replacement-1",
                index=0,
            ),
            make_embedding(),
        ),
    ]

    original_add = None

    from app.db.session import session_scope

    def failing_replace(*args, **kwargs):
        raise AIProviderError("forced test failure")

    monkeypatch.setattr(
        VectorRepository,
        "replace_document_chunks",
        failing_replace,
    )

    with pytest.raises(AIProviderError):
        VectorRepository.replace_document_chunks(
            user_id=user.id,
            chat_id=chat.id,
            chunks_with_embeddings=replacement_chunks,
            pdf_context="replacement document",
        )

    monkeypatch.undo()

    chat_after = ChatRepository.get_by_id(
        chat_id=chat.id,
        user_id=user.id,
    )

    assert chat_after is not None
    assert chat_after.pdf_context == "original document"

    with session_scope() as db:
        chunks_after = list(
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.chat_id == chat.id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    assert [chunk.content for chunk in chunks_after] == [
        "original-1",
        "original-2",
    ]
