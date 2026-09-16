"""
P3-09: Backend Production Stack Integration Verification Suite.

Validates the integrated production backend stack:
  FastAPI -> PostgreSQL + pgvector -> Redis/Limiter -> RAG/Reranker -> Provider Streaming
"""

import asyncio
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
# E2E-01: TENANT AUTHENTICATION & IDOR BOUNDARIES
# =====================================================================

def test_p3_09_e2e_01_idor_rejection_across_tenants(monkeypatch):
    """E2E-01: Cross-user chat access and deletion rejected (403/404)."""
    mock_user = MagicMock(id=10)
    app.dependency_overrides[get_current_user] = lambda: mock_user
    monkeypatch.setattr(ChatRepository, "get_by_id", lambda chat_id, user_id: None)
    monkeypatch.setattr(ChatRepository, "delete_chat", lambda chat_id, user_id: False)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        res_get = client.get("/chat/999")
        assert res_get.status_code in (403, 404)

        res_stream = client.post("/chat/stream", json={"chat_id": 999, "prompt": "probe"})
        assert res_stream.status_code in (403, 404)

        res_del = client.delete("/chat/999")
        assert res_del.status_code in (403, 404)
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# E2E-02: NON-RAG CHAT STREAMING LIFECYCLE
# =====================================================================

def test_p3_09_e2e_02_non_rag_streaming_journey(monkeypatch):
    """E2E-02: Non-RAG chat stream lifecycle (stream_started -> tokens -> stream_completed)."""
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
# E2E-03 & E2E-04: RAG GROUNDING, CITATIONS & COMPETING DOC ISOLATION
# =====================================================================

def test_p3_09_e2e_03_and_04_rag_isolation_with_competing_document(monkeypatch):
    """
    E2E-03 & E2E-04: Active Doc A is selected while competing Doc B exists.
    Retrieval receives candidate pool containing both Doc A and Doc B.
    Asserts:
      - Vector search query passes active document_id=101.
      - Competing Doc B chunks are filtered/excluded from retrieval and prompt context.
      - E2E-04: Citation metadata serialized into sources event with page numbers.
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

    # Active document is Doc A (id=101); competing document is Doc B (id=202)
    mock_doc_a = MagicMock(id=101, user_id=1, filename="DocAlpha.pdf")
    monkeypatch.setattr(DocumentRepository, "get_active_for_chat", lambda *args, **kwargs: mock_doc_a)

    captured_filter = {}
    def mock_search_hybrid(user_id, document_id, query_text, query_vector, **kwargs):
        captured_filter["user_id"] = user_id
        captured_filter["document_id"] = document_id
        # VectorRepository returns only chunks matching queried document_id
        all_tenant_chunks = [
            {"id": 1, "document_id": 101, "content": "Alpha authorized knowledge", "page_number": 3, "chunk_index": 2, "distance": 0.12, "rrf_score": 0.8},
            {"id": 2, "document_id": 202, "content": "Beta foreign secret leak", "page_number": 1, "chunk_index": 0, "distance": 0.05, "rrf_score": 0.9},
        ]
        return [c for c in all_tenant_chunks if c["document_id"] == document_id]

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
        
        full_system_context = "".join(captured_prompt)
        assert "Alpha authorized knowledge" in full_system_context
        assert "Beta foreign secret leak" not in full_system_context
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# E2E-05 & E2E-06: RERANKER OPERATIONAL PATHS (DISABLED, FALLBACK)
# =====================================================================

def test_p3_09_e2e_05_reranker_disabled_default_flow(monkeypatch):
    """E2E-05: ENABLE_RERANKING=False operational default bypasses RerankerService."""
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


def test_p3_09_e2e_06_reranker_enabled_and_fallback_journey(monkeypatch):
    """E2E-06: ENABLE_RERANKING=True falls back deterministically to unranked top-6 on failure."""
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
# E2E-07: PROVIDER FAILURE & ERROR RESPONSE SANITIZATION
# =====================================================================

def test_p3_09_e2e_07_provider_failure_and_response_sanitization(monkeypatch):
    """
    E2E-07: Provider crash yields sanitized stream_error event.
    Asserts SECRET_API_TOKEN_XYZ is redacted from client response payload.
    """
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
# E2E-08: PERSONA & CUSTOM INSTRUCTIONS INVARIANTS
# =====================================================================

def test_p3_09_e2e_08_persona_and_custom_instructions_grounding(monkeypatch):
    """E2E-08: Persona and custom instructions injected cleanly into system prompt."""
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


# =====================================================================
# E2E-09: REAL CLIENT DISCONNECT / CANCELLATION HARNESS
# =====================================================================

def test_p3_09_e2e_09_client_cancellation_suppresses_phantom_messages(monkeypatch):
    """
    E2E-09: Mid-stream client disconnect simulation.
    Exercises the production route boundary:
      - Stream starts and yields first token.
      - Client disconnects; request.is_disconnected() returns True.
      - Endpoint logs ai_stream_cancelled and raises asyncio.CancelledError.
      - Asserts exactly 0 assistant messages persisted in chat history.
      - Asserts subsequent /chat/stream request recovers and completes successfully.
    """
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

    persisted_messages = []
    def mock_add_msg(chat_id, user_id=1, role="user", content="", **kwargs):
        msg = MagicMock(id=len(persisted_messages) + 1, role=role, content=content)
        persisted_messages.append(msg)
        return msg

    monkeypatch.setattr(ChatRepository, "add_message", mock_add_msg)

    # 1. First run: client disconnects mid-stream
    disconnect_flag = False

    async def mock_disconnect_stream(*args, **kwargs):
        yield "Initial chunk "
        nonlocal disconnect_flag
        disconnect_flag = True
        yield "Second chunk "

    mock_provider = MagicMock()
    mock_provider.generate_stream = mock_disconnect_stream
    monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_provider)

    from starlette.requests import Request
    original_is_disconnected = Request.is_disconnected

    async def mock_is_disconnected(self):
        if disconnect_flag:
            return True
        return await original_is_disconnected(self)

    monkeypatch.setattr(Request, "is_disconnected", mock_is_disconnected)

    try:
        client = TestClient(app, raise_server_exceptions=False)
        # Trigger cancellation stream
        res_cancel = client.post("/chat/stream", json={"chat_id": 96, "prompt": "Cancel mid way"})
        assert res_cancel.status_code == 200

        # Verify zero assistant messages were persisted
        ai_messages = [m for m in persisted_messages if getattr(m, "role", None) == "ai"]
        assert len(ai_messages) == 0

        # 2. Recovery: subsequent chat stream succeeds normally
        disconnect_flag = False
        async def mock_clean_stream(*args, **kwargs):
            yield "Recovered token"

        mock_clean_provider = MagicMock()
        mock_clean_provider.generate_stream = mock_clean_stream
        monkeypatch.setattr(LLMProviderFactory, "get_provider", lambda *args, **kwargs: mock_clean_provider)

        res_recovery = client.post("/chat/stream", json={"chat_id": 96, "prompt": "Subsequent clean request"})
        assert res_recovery.status_code == 200
        assert "Recovered token" in res_recovery.text

        # Exactly one assistant message persisted from successful recovery turn
        ai_messages_after_recovery = [m for m in persisted_messages if getattr(m, "role", None) == "ai"]
        assert len(ai_messages_after_recovery) == 1
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# E2E-10: UNAUTHENTICATED ROUTE REJECTION
# =====================================================================

def test_p3_09_e2e_10_unauthenticated_requests_blocked():
    """E2E-10: Unauthenticated callers receive HTTP 401 across all protected routes."""
    app.dependency_overrides.clear()
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/chat/all").status_code == 401
    assert client.post("/chat/stream", json={"chat_id": 1, "prompt": "Hi"}).status_code == 401
    assert client.delete("/chat/1").status_code == 401
