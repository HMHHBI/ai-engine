from __future__ import annotations

from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.models import Chat, User, UserPlan
from app.repositories.chat_repo import ChatRepository


def _create_user(db, email: str = "citation_user@example.com") -> User:
    user = User(
        name="Citation Tester",
        email=email,
        password=hash_password("Secret123!"),
        plan=UserPlan.FREE,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_add_message_persists_sources_metadata(db_session):
    user = _create_user(db_session, "persist_meta@example.com")
    chat = Chat(
        user_id=user.id,
        title="Citation Persistence Test",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    mock_sources = [
        {"id": 101, "page_number": 2, "chunk_index": 0, "distance": 0.123456},
        {"id": 102, "page_number": 5, "chunk_index": 3, "distance": 0.456789},
    ]

    msg = ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user.id,
        role="ai",
        content="This answer is grounded in two citations.",
        sources=mock_sources,
    )

    assert msg is not None
    assert msg.sources is not None
    assert len(msg.sources) == 2
    assert msg.sources[0]["id"] == 101
    assert msg.sources[0]["page_number"] == 2
    assert msg.sources[1]["chunk_index"] == 3


def test_add_message_handles_none_sources_as_null(db_session):
    user = _create_user(db_session, "null_meta@example.com")
    chat = Chat(
        user_id=user.id,
        title="Null Citation Test",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    msg = ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user.id,
        role="user",
        content="Regular message without sources",
        sources=None,
    )

    assert msg is not None
    assert msg.sources is None


def test_get_chat_history_hydrates_sources(client: TestClient, db_session):
    user = _create_user(db_session, "hydrate_user@example.com")
    chat = Chat(
        user_id=user.id,
        title="Hydration Endpoint Test",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    mock_sources = [{"id": 42, "page_number": 1, "chunk_index": 2, "distance": 0.25}]

    ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user.id,
        role="ai",
        content="Response with citation",
        sources=mock_sources,
    )

    token = create_access_token(user_id=user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        f"/chat/{chat.id}",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "sources" in data[0]
    assert data[0]["sources"] is not None
    assert data[0]["sources"][0]["id"] == 42
    assert data[0]["sources"][0]["page_number"] == 1


def test_cross_user_cannot_hydrate_sources(client: TestClient, db_session):
    user_a = _create_user(db_session, "owner_a@example.com")
    user_b = _create_user(db_session, "intruder_b@example.com")

    chat = Chat(
        user_id=user_a.id,
        title="User A Chat",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    mock_sources = [{"id": 99, "page_number": 1, "chunk_index": 0, "distance": 0.1}]

    ChatRepository.add_message(
        chat_id=chat.id,
        user_id=user_a.id,
        role="ai",
        content="Private AI message",
        sources=mock_sources,
    )

    token_b = create_access_token(user_id=user_b.id)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    response = client.get(
        f"/chat/{chat.id}",
        headers=headers_b,
    )

    assert response.status_code == 404


def test_stream_persists_sources_on_successful_completion(
    client: TestClient, db_session
):
    user = _create_user(db_session, "stream_user@example.com")
    chat = Chat(
        user_id=user.id,
        title="Streaming Persistence Test",
        pdf_context="Sample indexed doc",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)

    mock_chunks = [
        {
            "id": 10,
            "page_number": 3,
            "chunk_index": 1,
            "distance": 0.15,
            "content": "Sample context passage",
        }
    ]

    async def mock_stream(*args, **kwargs):
        yield "Answer "
        yield "derived from chunk."

    with patch(
        "app.services.embedding_service.EmbeddingService.generate_embedding",
        new=AsyncMock(return_value=[0.1] * 768),
    ), patch(
        "app.repositories.vector_repo.VectorRepository.search_similar_chunks",
        return_value=mock_chunks,
    ), patch(
        "app.services.providers.factory.LLMProviderFactory.get_provider"
    ) as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.generate_stream = mock_stream
        mock_factory.return_value = mock_provider

        token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            "/chat/stream",
            json={"chat_id": chat.id, "prompt": "What does the doc say?"},
            headers=headers,
        )

        assert response.status_code == 200

    history = ChatRepository.get_history(chat_id=chat.id, user_id=user.id)
    ai_messages = [m for m in history if m.role in ("ai", "assistant")]
    assert len(ai_messages) == 1
    assert ai_messages[0].sources is not None
    assert len(ai_messages[0].sources) == 1
    assert ai_messages[0].sources[0]["id"] == 10
    assert ai_messages[0].sources[0]["page_number"] == 3
