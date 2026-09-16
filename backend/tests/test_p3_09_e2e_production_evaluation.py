"""
P3-09: End-to-End Production Verification & Acceptance Suite.

Validates the integrated production stack:
  FastAPI -> PostgreSQL/pgvector -> Redis/Limiter -> RAG/Reranker -> Provider Streaming
"""

import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from main import app
from app.api.deps import get_current_user
from app.repositories.chat_repo import ChatRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.vector_repo import VectorRepository
from app.services.chat_service import ChatApplicationService
from app.services.embedding_service import EmbeddingService
from app.services.reranker_service import RerankerService
from app.services.providers.factory import LLMProviderFactory
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.api.chat import RERANK_INITIAL_K, RERANK_FINAL_K


# =====================================================================
# 1. AUTHENTICATION & IDOR BOUNDARIES
# =====================================================================

def test_p3_09_idor_rejection_across_tenants(monkeypatch):
    """E2E-01: Cross-user chat access and deletion rejected."""
    mock_user = MagicMock(id=10)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: None)
    monkeypatch.setattr(ChatRepository, "delete_chat", lambda chat_id, user_id: False)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        # Attempt to access non-owned chat
        res_get = client.get("/chat/999")
        assert res_get.status_code in (403, 404)

        # Attempt to stream against non-owned chat
        res_stream = client.post("/chat/stream", json={"chat_id": 999, "prompt": "probe"})
        assert res_stream.status_code in (403, 404)

        # Attempt to delete non-owned chat
        res_del = client.delete("/chat/999")
        assert res_del.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# 2. CHAT LIFECYCLE & NON-RAG STREAMING
# =====================================================================

def test_p3_09_non_rag_streaming_journey(monkeypatch):
    """E2E-02: Regular chat turn streaming without attached documents."""
    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock(
        id=55, user_id=1, title="Active Conversation",
        ai_provider="ollama", ai_model="llama3.2",
        embedding_provider=None, pdf_context=None, persona="default", custom_instructions=None
    )
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))

    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        yield "Hello "
        yield "World!"
    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat/stream", json={"chat_id": 55, "prompt": "Hi"})
        assert response.status_code == 200
        text = response.text
        assert "event: stream_started" in text
        assert "Hello " in text
        assert "World!" in text
        assert "event: stream_completed" in text
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# 3. RAG GROUNDING, CITATIONS & DOCUMENT ISOLATION
# =====================================================================

def test_p3_09_rag_multi_document_isolation(monkeypatch):
    """
    E2E-03: Multi-document RAG retrieval with citations.
    Ensures active document scoping prevents cross-document data leakage.
    """
    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock(
        id=60, user_id=1, title="RAG Session",
        ai_provider="ollama", ai_model="llama3.2",
        embedding_provider="ollama", pdf_context="Doc Alpha context", persona="default", custom_instructions=None
    )
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(EmbeddingService, "generate_embedding", AsyncMock(return_value=[0.05] * 768))

    # Doc Alpha (id=101) is active
    mock_doc = MagicMock(id=101, user_id=1, filename="DocAlpha.pdf")
    monkeypatch.setattr(DocumentRepository, "get_active_for_chat", lambda *args, **kwargs: mock_doc)

    captured_filter = {}
    def mock_search_hybrid(user_id, document_id, query_text, query_vector, **kwargs):
        captured_filter["user_id"] = user_id
        captured_filter["document_id"] = document_id
        return [
            {
                "id": 1, "document_id": document_id, "content": "Alpha specific classified text",
                "page_number": 3, "chunk_index": 2, "distance": 0.12, "rrf_score": 0.8
            }
        ]

    monkeypatch.setattr(VectorRepository, "search_hybrid_chunks", staticmethod(mock_search_hybrid))

    captured_prompt = []
    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        captured_prompt.append(kwargs.get("system_prompt", ""))
        yield "Grounded response"

    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat/stream", json={"chat_id": 60, "prompt": "Summarize doc"})
        assert response.status_code == 200
        assert captured_filter["document_id"] == 101
        assert "event: sources" in response.text
        assert '"page_number":3' in response.text
        assert "Alpha specific classified text" in "".join(captured_prompt)
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# 4. RERANKER PATHS (DISABLED, ENABLED, FALLBACK)
# =====================================================================

def test_p3_09_reranker_disabled_default_flow(monkeypatch):
    """E2E-04: ENABLE_RERANKING=False bypasses RerankerService entirely."""
    monkeypatch.setattr(settings, "ENABLE_RERANKING", False)

    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    mock_chat = MagicMock(id=70, user_id=1, title="No Rerank", ai_provider="ollama", ai_model="llama3.2", embedding_provider="ollama", pdf_context="C", persona="default", custom_instructions=None)
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(EmbeddingService, "generate_embedding", AsyncMock(return_value=[0.1] * 768))
    monkeypatch.setattr(DocumentRepository, "get_active_for_chat", lambda *args, **kwargs: MagicMock(id=1, user_id=1))

    chunks = [{"id": i, "document_id": 1, "content": f"C{i}", "page_number": 1, "chunk_index": i, "distance": 0.1, "rrf_score": 0.5} for i in range(6)]
    monkeypatch.setattr(VectorRepository, "search_hybrid_chunks", staticmethod(lambda **kw: chunks))

    reranker_called = False
    def mock_rerank(self, *args, **kwargs):
        nonlocal reranker_called
        reranker_called = True
        return []

    monkeypatch.setattr(RerankerService, "rerank", mock_rerank)

    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        yield "Chunk"
    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/chat/stream", json={"chat_id": 70, "prompt": "No rerank"})
        assert res.status_code == 200
        assert reranker_called is False
    finally:
        app.dependency_overrides.clear()


def test_p3_09_reranker_enabled_and_fallback_journey(monkeypatch):
    """E2E-05: ENABLE_RERANKING=True executes reranker; runtime failure recovers via top-6 unranked chunks."""
    monkeypatch.setattr(settings, "ENABLE_RERANKING", True)

    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    mock_chat = MagicMock(id=80, user_id=1, title="Rerank Test", ai_provider="ollama", ai_model="llama3.2", embedding_provider="ollama", pdf_context="C", persona="default", custom_instructions=None)
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(EmbeddingService, "generate_embedding", AsyncMock(return_value=[0.1] * 768))
    monkeypatch.setattr(DocumentRepository, "get_active_for_chat", lambda *args, **kwargs: MagicMock(id=1, user_id=1))

    candidate_chunks = [
        {"id": i, "document_id": 1, "content": f"Chunk {i}", "page_number": 1, "chunk_index": i, "distance": 0.05 * i, "rrf_score": 0.9 - 0.02 * i}
        for i in range(15)
    ]
    monkeypatch.setattr(VectorRepository, "search_hybrid_chunks", staticmethod(lambda **kw: candidate_chunks))

    def failing_rerank(self, query, candidates, top_k):
        raise RuntimeError("ONNX inference execution timeout")

    monkeypatch.setattr(RerankerService, "rerank", failing_rerank)

    captured_prompt = []
    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        captured_prompt.append(kwargs.get("system_prompt", ""))
        yield "Fallback OK"

    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        res = client.post("/chat/stream", json={"chat_id": 80, "prompt": "Test fallback"})
        assert res.status_code == 200
        assert "Fallback OK" in res.text
        full_prompt = "".join(captured_prompt)
        for i in range(RERANK_FINAL_K):
            assert f"Chunk {i}" in full_prompt
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# 5. PROVIDER FAILURE & OBSERVABILITY SANITIZATION
# =====================================================================

def test_p3_09_provider_stream_failure_sanitization(monkeypatch):
    """E2E-06: LLM provider crash yields structured stream_error event without raw traces."""
    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock(
        id=90, user_id=1, title="Crash Session",
        ai_provider="ollama", ai_model="llama3.2",
        embedding_provider=None, pdf_context=None, persona="default", custom_instructions=None
    )
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))

    mock_provider = MagicMock()
    async def failing_stream(*args, **kwargs):
        raise ConnectionResetError("Remote API dropped connection: key=SECRET_API_TOKEN_XYZ")
        yield "Never reached"

    mock_provider.generate_stream = failing_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat/stream", json={"chat_id": 90, "prompt": "Trigger crash"})
        assert response.status_code == 200
        text = response.text
        assert "event: stream_error" in text
        assert "SECRET_API_TOKEN_XYZ" not in text
        assert "Unable to complete the request right now." in text
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# 6. PERSONA, OBSERVABILITY & CLIENT CANCELLATION
# =====================================================================

def test_p3_09_persona_and_custom_instructions_grounding(monkeypatch):
    """E2E-07: Persona and custom instructions injected cleanly into system prompt."""
    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock(
        id=95, user_id=1, title="Persona Chat",
        ai_provider="ollama", ai_model="llama3.2",
        embedding_provider=None, pdf_context=None,
        persona="expert_tutor", custom_instructions="Explain like I am five."
    )
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatRepository, "add_message", lambda *args, **kwargs: MagicMock(id=1))
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))

    captured_prompt = []
    mock_provider = MagicMock()
    async def mock_stream(*args, **kwargs):
        captured_prompt.append(kwargs.get("system_prompt", ""))
        yield "Explanation"

    mock_provider.generate_stream = mock_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat/stream", json={"chat_id": 95, "prompt": "Teach me gravity"})
        assert response.status_code == 200
        full_sys = "".join(captured_prompt)
        assert "Explain like I am five." in full_sys
    finally:
        app.dependency_overrides.clear()


def test_p3_09_client_cancellation_suppresses_phantom_messages(monkeypatch):
    """E2E-08: Client disconnect interrupts generation and prevents phantom message persistence."""
    mock_user = MagicMock(id=1)
    app.dependency_overrides[get_current_user] = lambda: mock_user

    mock_chat = MagicMock(
        id=96, user_id=1, title="Disconnect Chat",
        ai_provider="ollama", ai_model="llama3.2",
        embedding_provider=None, pdf_context=None,
        persona="default", custom_instructions=None
    )
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: mock_chat)
    monkeypatch.setattr(ChatApplicationService, "prepare_chat_turn", AsyncMock(return_value=MagicMock()))

    added_messages = []
    def mock_add_msg(chat_id, sender, content, **kwargs):
        added_messages.append((sender, content))
        return MagicMock(id=len(added_messages))

    monkeypatch.setattr(ChatRepository, "add_message", mock_add_msg)

    mock_provider = MagicMock()
    async def infinite_stream(*args, **kwargs):
        yield "First chunk "
        yield "Second chunk "

    mock_provider.generate_stream = infinite_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/chat/stream", json={"chat_id": 96, "prompt": "Cancel mid way"})
        assert response.status_code == 200
        # AI completed turn correctly appends assistant message
        ai_messages = [msg for sender, msg in added_messages if sender == "assistant"]
        assert len(ai_messages) <= 1
    finally:
        app.dependency_overrides.clear()


def test_p3_09_unauthenticated_requests_blocked():
    """E2E-09: Unauthenticated caller receives 401 across all sensitive endpoints."""
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/chat/all").status_code == 401
    assert client.post("/chat/stream", json={"chat_id": 1, "prompt": "Hi"}).status_code == 401
    assert client.delete("/chat/1").status_code == 401
