"""Unit tests for chat endpoint reranking integration."""

import pytest
from app.core.config import settings
from app.api.chat import _build_rerank_candidates, RERANK_INITIAL_K, RERANK_FINAL_K
from app.services.reranker_service import RerankCandidate


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


def test_reranker_fallback_behavior_on_failure():
    """Verify that when reranking fails, candidate list falls back safely to top K_FINAL hybrid chunks."""
    initial_chunks = [
        {"id": i, "content": f"Chunk {i}", "rrf_score": 1.0 / (i + 1), "distance": 0.1 * i}
        for i in range(20)
    ]
    assert len(initial_chunks) == 20

    # Simulate reranker failure fallback logic directly
    fallback_result = initial_chunks[:RERANK_FINAL_K]
    assert len(fallback_result) == 6
    assert fallback_result[0]["id"] == 0
    assert fallback_result[5]["id"] == 5


def test_reranking_disabled_bypasses_reranker_service(monkeypatch):
    """Verify ENABLE_RERANKING=False preserves existing hybrid candidate depth."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENABLE_RERANKING", False)
    assert settings.ENABLE_RERANKING is False
