"""Integration tests for chat endpoint reranker integration, safety flags, and fallback."""

import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from main import app
from app.api.deps import get_current_user
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.vector_repo import VectorRepository
from app.services.chat_service import ChatApplicationService
from app.services.embedding_service import EmbeddingService
from app.services.reranker_service import RerankCandidate, RerankerService
from app.services.providers.factory import LLMProviderFactory
from app.api.chat import (
    _build_rerank_candidates,
    RERANK_INITIAL_K,
    RERANK_FINAL_K,
)


def test_build_rerank_candidates_preserves_contract():
    chunks = [
        {
            "id": 42,
            "document_id": 7,
            "content": "Sample content text",
            "page_number": 2,
            "chunk_index": 0,
            "distance": 0.15,
            "rrf_score": 0.016,
        }
    ]
    candidates = _build_rerank_candidates(chunks)
    assert len(candidates) == 1
    assert candidates[0].chunk_id == 42
    assert candidates[0].content == "Sample content text"
    assert candidates[0].metadata["page_number"] == 2
    assert candidates[0].metadata["document_id"] == 7
    assert candidates[0].metadata["distance"] == 0.15


def test_constants_depth():
    assert RERANK_INITIAL_K == 20
    assert RERANK_FINAL_K == 6


def test_reranking_default_is_disabled():
    assert settings.ENABLE_RERANKING is False


def test_create_reranker_provider_returns_cross_encoder(monkeypatch):
    from app.services.reranker_service import create_reranker_provider, CrossEncoderRerankerProvider
    monkeypatch.setattr(settings, "RERANKER_PROVIDER", "cross_encoder")
    provider = create_reranker_provider()
    assert isinstance(provider, CrossEncoderRerankerProvider)


def test_create_reranker_provider_returns_deterministic(monkeypatch):
    from app.services.reranker_service import create_reranker_provider, DeterministicRerankerProvider
    monkeypatch.setattr(settings, "RERANKER_PROVIDER", "deterministic")
    provider = create_reranker_provider()
    assert isinstance(provider, DeterministicRerankerProvider)


def test_chat_stream_reranker_fallback_on_inference_failure(monkeypatch):
    """
    Exercise the real chat endpoint ai_stream() execution path:
    Force RerankerService.rerank to raise an unexpected runtime exception.
    Verify that:
    1. The endpoint catches the exception and does NOT return an HTTP 500 error.
    2. Sources event contains exactly RERANK_FINAL_K (6) items.
    3. Source IDs preserve the original hybrid rank order (0 through 5).
    """
    mock_user = MagicMock()
    mock_user.id = 1
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock()
    mock_chat.id = 100
    mock_chat.user_id = 1
    mock_chat.title = "Test Chat"
    mock_chat.ai_provider = "ollama"
    mock_chat.ai_model = "ollama-llama3.2"
    mock_chat.embedding_provider = "ollama"
    mock_chat.pdf_context = "Indexed File: test.pdf"
    mock_chat.persona = "default"
    mock_chat.custom_instructions = None

    monkeypatch.setattr(ChatRepository, "get_by_id", lambda *args, **kwargs: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=999))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(EmbeddingService, "generate_embedding", AsyncMock(return_value=[0.1] * 768))

    mock_doc = MagicMock()
    mock_doc.id = 200
    monkeypatch.setattr(DocumentRepository, "get_active_for_chat", lambda *args, **kwargs: mock_doc)

    hybrid_candidates = [
        {
            "id": i,
            "document_id": 200,
            "content": f"Hybrid candidate passage content {i}",
            "page_number": 1,
            "chunk_index": i,
            "distance": 0.05 * i,
            "rrf_score": 1.0 / (i + 1),
            "score": 1.0 / (i + 1),
        }
        for i in range(20)
    ]
    monkeypatch.setattr(VectorRepository, "search_hybrid_chunks", lambda *args, **kwargs: list(hybrid_candidates))

    def failing_rerank(*args, **kwargs):
        raise RuntimeError("Simulated CrossEncoder fatal model/inference crash")

    monkeypatch.setattr(RerankerService, "rerank", failing_rerank)
    monkeypatch.setattr(settings, "ENABLE_RERANKING", True)

    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        yield "Test response grounded in fallback context"
    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app)
        response = client.post(
            "/chat/stream",
            json={"chat_id": 100, "prompt": "What is the policy?"},
        )

        assert response.status_code == 200

        events: list[tuple[str, dict]] = []
        for block in response.text.strip().split("\n\n"):
            lines = block.strip().split("\n")
            event_name = ""
            event_data = {}
            for line in lines:
                if line.startswith("event: "):
                    event_name = line.replace("event: ", "").strip()
                elif line.startswith("data: "):
                    event_data = json.loads(line.replace("data: ", "").strip())
            if event_name:
                events.append((event_name, event_data))

        event_names = [e[0] for e in events]
        assert "stream_error" not in event_names
        assert "sources" in event_names

        sources_event = next(e[1] for e in events if e[0] == "sources")
        sources = sources_event.get("sources", [])

        assert len(sources) == RERANK_FINAL_K
        for idx, src in enumerate(sources):
            assert src["id"] == idx

    finally:
        app.dependency_overrides.clear()
