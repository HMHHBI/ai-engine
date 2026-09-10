import pytest
from scripts.evaluations.rag_quality_eval import (
    EvaluationQuery,
    RetrievedChunk,
    assert_test_database,
    calculate_query_metrics,
    context_precision_at_k,
    context_recall_at_k,
    hit_rate_at_k,
    reciprocal_rank_at_k,
    build_failures,
)


def make_query() -> EvaluationQuery:
    return EvaluationQuery(
        query_id="test-001",
        user_id=1,
        document_id=10,
        query="test query",
        relevant_chunk_ids=frozenset({102, 104}),
    )


def make_results() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(chunk_id=101, document_id=10, chunk_index=0, content="irrelevant", distance=0.10),
        RetrievedChunk(chunk_id=102, document_id=10, chunk_index=1, content="relevant", distance=0.12),
        RetrievedChunk(chunk_id=103, document_id=10, chunk_index=2, content="irrelevant", distance=0.15),
        RetrievedChunk(chunk_id=104, document_id=10, chunk_index=3, content="relevant", distance=0.17),
    ]


def test_safety_guardrail_blocks_non_test_db():
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY VIOLATION"):
        assert_test_database("postgresql://postgres:pass@localhost:5432/hassan_ai_db")


def test_safety_guardrail_allows_test_db():
    assert_test_database("postgresql://postgres:pass@localhost:5432/hassan_ai_test")
    assert_test_database("postgresql://postgres:pass@localhost:5432/test_rag")


def test_hit_rate_at_k():
    query = make_query()
    results = make_results()
    assert hit_rate_at_k(results, query, 1) == 0.0
    assert hit_rate_at_k(results, query, 2) == 1.0


def test_reciprocal_rank_at_k():
    query = make_query()
    results = make_results()
    assert reciprocal_rank_at_k(results, query, 1) == 0.0
    assert reciprocal_rank_at_k(results, query, 2) == 0.5


def test_context_precision_at_k():
    query = make_query()
    results = make_results()
    assert context_precision_at_k(results, query, 1) == 0.0
    assert context_precision_at_k(results, query, 2) == 0.5
    assert context_precision_at_k(results, query, 4) == 0.5


def test_context_recall_at_k_exact():
    query = make_query()
    results = make_results()
    assert context_recall_at_k(results, query, 1) == 0.0
    assert context_recall_at_k(results, query, 2) == 0.5
    assert context_recall_at_k(results, query, 3) == 0.5
    assert context_recall_at_k(results, query, 4) == 1.0


def test_calculate_query_metrics():
    query = make_query()
    results = make_results()
    metrics = calculate_query_metrics(results, query, (1, 3, 5))
    assert metrics["1"]["hit_rate"] == 0.0
    assert metrics["3"]["hit_rate"] == 1.0
    assert metrics["3"]["mrr"] == 0.5
    assert metrics["5"]["context_recall"] == 1.0


def test_build_failures():
    passing_aggregate = {
        "1": {"hit_rate": 0.75},
        "3": {"hit_rate": 0.90},
        "5": {"hit_rate": 0.95, "mrr": 0.85},
        "10": {"hit_rate": 0.98},
    }
    assert len(build_failures(passing_aggregate)) == 0
