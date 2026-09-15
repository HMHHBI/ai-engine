"""Unit tests for P3-05 multi-strategy retrieval and reranking evaluation extensions."""

import pytest
from unittest.mock import MagicMock
from scripts.evaluations.rag_quality_eval import (
    validate_strategies,
    build_rerank_candidates,
    apply_reranking,
    EvaluationQuery,
    RETRIEVAL_STRATEGIES,
)
from app.services.reranker_service import RerankerService


def test_validate_strategies_accepts_valid():
    assert validate_strategies(["dense", "hybrid_rerank"]) == ("dense", "hybrid_rerank")


def test_validate_strategies_rejects_invalid():
    with pytest.raises(ValueError, match="Unsupported retrieval strategy"):
        validate_strategies(["dense", "invalid_strategy"])


def test_validate_strategies_rejects_duplicates():
    with pytest.raises(ValueError, match="Retrieval strategies must be unique"):
        validate_strategies(["dense", "dense"])


def test_validate_strategies_rejects_empty():
    with pytest.raises(ValueError, match="At least one retrieval strategy is required"):
        validate_strategies([])


def test_build_rerank_candidates_preserves_metadata():
    results = [
        {
            "id": 101,
            "document_id": 10,
            "chat_id": 5,
            "chunk_index": 2,
            "page_number": 1,
            "content": "test chunk content",
            "rrf_score": 0.033,
        }
    ]
    candidates = build_rerank_candidates(results)
    assert len(candidates) == 1
    assert candidates[0].chunk_id == 101
    assert candidates[0].content == "test chunk content"
    assert candidates[0].score == 0.033
    assert candidates[0].metadata["document_id"] == 10
    assert candidates[0].metadata["chunk_index"] == 2


def test_apply_reranking_returns_top_k_retrieved():
    query = EvaluationQuery(
        query_id="q1",
        user_id=1,
        document_id=10,
        query="PostgreSQL",
        relevant_chunk_ids=(102,),
    )
    candidates = [
        {"id": 101, "document_id": 10, "content": "Unrelated topic", "rrf_score": 0.03},
        {"id": 102, "document_id": 10, "content": "PostgreSQL database configuration", "rrf_score": 0.02},
    ]
    retrieved, latency = apply_reranking(query, candidates, RerankerService())
    assert len(retrieved) == 2
    assert retrieved[0].chunk_id == 102
    assert latency >= 0.0


def test_validate_strategies_accepts_hybrid_cross_encoder_rerank():
    assert "hybrid_cross_encoder_rerank" in RETRIEVAL_STRATEGIES
    assert validate_strategies(["hybrid_cross_encoder_rerank"]) == ("hybrid_cross_encoder_rerank",)


def test_apply_reranking_with_cross_encoder_mock():
    from app.services.reranker_service import BaseRerankerProvider

    class MockCrossEncoderProvider(BaseRerankerProvider):
        def score(self, query, candidates):
            # Candidate 202 ko highest score do
            return [0.10 if c.chunk_id == 201 else 0.95 for c in candidates]

    query = EvaluationQuery(
        query_id="q_ce_1",
        user_id=1,
        document_id=10,
        query="Cross-Encoder ranking test",
        relevant_chunk_ids=(202,),
    )
    candidates = [
        {"id": 201, "document_id": 10, "content": "Low relevance chunk", "rrf_score": 0.05},
        {"id": 202, "document_id": 10, "content": "High relevance chunk", "rrf_score": 0.01},
    ]

    service = RerankerService(provider=MockCrossEncoderProvider())
    retrieved, latency_ms = apply_reranking(query, candidates, service)

    assert len(retrieved) == 2
    assert retrieved[0].chunk_id == 202
    assert retrieved[0].rerank_score == 0.95
    assert retrieved[1].chunk_id == 201
    assert latency_ms >= 0.0
