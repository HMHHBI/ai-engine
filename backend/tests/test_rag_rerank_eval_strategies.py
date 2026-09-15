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
