from scripts.evaluations.rag_quality_eval import (
    EvaluationQuery, RetrievedChunk, calculate_query_metrics,
    context_precision_at_k, context_recall_at_k, hit_rate_at_k,
    reciprocal_rank_at_k, build_failures
)

def make_query():
    return EvaluationQuery(
        query_id="test-001", user_id=1, document_id=10, query="test",
        relevant_chunk_indexes=frozenset({3, 7}), relevant_chunk_ids=frozenset()
    )

def make_results():
    return [
        RetrievedChunk(chunk_id=101, document_id=10, chunk_index=2, content="a", distance=0.10),
        RetrievedChunk(chunk_id=102, document_id=10, chunk_index=3, content="b", distance=0.12),
        RetrievedChunk(chunk_id=103, document_id=10, chunk_index=8, content="c", distance=0.15),
        RetrievedChunk(chunk_id=104, document_id=10, chunk_index=7, content="d", distance=0.17),
    ]

def test_hit_rate_at_k():
    q, r = make_query(), make_results()
    assert hit_rate_at_k(r, q, 1) == 0.0
    assert hit_rate_at_k(r, q, 2) == 1.0

def test_reciprocal_rank_at_k():
    q, r = make_query(), make_results()
    assert reciprocal_rank_at_k(r, q, 1) == 0.0
    assert reciprocal_rank_at_k(r, q, 2) == 0.5

def test_context_precision_at_k():
    q, r = make_query(), make_results()
    assert context_precision_at_k(r, q, 1) == 0.0
    assert context_precision_at_k(r, q, 2) == 0.5

def test_context_recall_at_k():
    q, r = make_query(), make_results()
    assert context_recall_at_k(r, q, 1) == 0.0
    assert context_recall_at_k(r, q, 4) == 1.0

def test_calculate_query_metrics():
    q, r = make_query(), make_results()
    m = calculate_query_metrics(r, q, (1, 3, 5))
    assert m["1"]["hit_rate"] == 0.0
    assert m["3"]["hit_rate"] == 1.0

def test_build_failures():
    agg = {"1": {"hit_rate": 0.75}, "3": {"hit_rate": 0.90}, "5": {"hit_rate": 0.95, "mrr": 0.85}, "10": {"hit_rate": 0.98}}
    assert len(build_failures(agg)) == 0
