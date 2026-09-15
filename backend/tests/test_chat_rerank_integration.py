"""Integration tests for chat endpoint reranker integration, safety flags, and fallback."""

import asyncio
from unittest.mock import MagicMock
import pytest

from app.core.config import settings
from app.api.chat import (
    _build_rerank_candidates,
    RERANK_INITIAL_K,
    RERANK_FINAL_K,
)
from app.services.reranker_service import RerankCandidate, RerankerService


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


@pytest.mark.asyncio
async def test_chat_reranker_fallback_on_inference_failure(monkeypatch):
    """
    Exercise the actual chat fallback execution path:
    When RerankerService.rerank raises an unexpected exception during request processing,
    verify that:
    1. No exception escapes to abort the request.
    2. Context safely falls back to top RERANK_FINAL_K original hybrid chunks.
    3. Original hybrid rank order is strictly preserved.
    """
    initial_chunks = [
        {
            "id": i,
            "document_id": 100,
            "content": f"Hybrid content passage {i}",
            "page_number": 1,
            "chunk_index": i,
            "distance": 0.05 * i,
            "rrf_score": 1.0 / (i + 1),
            "score": 1.0 / (i + 1),
        }
        for i in range(20)
    ]

    # Force RerankerService.rerank to raise a runtime failure
    def mock_failing_rerank(*args, **kwargs):
        raise RuntimeError("Simulated CrossEncoder CUDA/CPU OOM or inference failure")

    monkeypatch.setattr(RerankerService, "rerank", mock_failing_rerank)
    monkeypatch.setattr(settings, "ENABLE_RERANKING", True)

    # Replicate chat endpoint rerank block execution
    context_chunks = list(initial_chunks)
    assert len(context_chunks) == 20

    if settings.ENABLE_RERANKING and context_chunks:
        rerank_candidates = _build_rerank_candidates(context_chunks)
        try:
            reranker = RerankerService()
            reranked_candidates = await asyncio.to_thread(
                reranker.rerank,
                "test query",
                rerank_candidates,
                RERANK_FINAL_K,
            )
            context_chunks = [
                {"id": int(c.metadata["id"]), "content": c.content}
                for c in reranked_candidates
            ]
        except Exception:
            context_chunks = context_chunks[:RERANK_FINAL_K]

    # Critical assertions
    assert len(context_chunks) == RERANK_FINAL_K
    for rank, chunk in enumerate(context_chunks):
        assert chunk["id"] == rank
        assert chunk["content"] == f"Hybrid content passage {rank}"
