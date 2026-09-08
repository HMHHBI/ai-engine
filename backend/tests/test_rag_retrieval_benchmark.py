import pytest
from unittest.mock import patch
from scripts.benchmarks.rag_retrieval_benchmark import (
    generate_synthetic_unit_vector,
    extract_scan_nodes,
    verify_retrieval_isolation_and_invariants,
)

def test_generate_synthetic_unit_vector():
    vec = generate_synthetic_unit_vector(768)
    assert len(vec) == 768
    norm = sum(x * x for x in vec) ** 0.5
    assert 0.99 <= norm <= 1.01

def test_extract_scan_nodes():
    plan_dict = {
        "Node Type": "Limit",
        "Plans": [
            {
                "Node Type": "Bitmap Heap Scan",
                "Relation Name": "document_chunks",
                "Plans": [
                    {
                        "Node Type": "Bitmap Index Scan",
                        "Index Name": "ix_document_chunks_document_id",
                    }
                ]
            }
        ]
    }
    nodes = extract_scan_nodes(plan_dict)
    assert len(nodes) == 2
    assert "Bitmap Heap Scan on document_chunks" in nodes[0]
    assert "Bitmap Index Scan using ix_document_chunks_document_id" in nodes[1]

def test_verify_retrieval_isolation_mocked():
    query_vec = [0.1] * 768

    def mock_search(user_id, document_id, query_vector, top_k=6, **kwargs):
        if user_id == 1 and document_id == 10:
            return [
                {"id": 1, "document_id": 10, "distance": 0.1},
                {"id": 2, "document_id": 10, "distance": 0.15},
            ]
        elif user_id == 1 and document_id == 20:
            return [
                {"id": 3, "document_id": 20, "distance": 0.12},
            ]
        # Cross-user returns empty
        return []

    with patch("app.repositories.vector_repo.VectorRepository.search_similar_chunks", side_effect=mock_search):
        invariants = verify_retrieval_isolation_and_invariants(
            owner_id=1,
            unauth_id=2,
            owner_doc_a_id=10,
            owner_doc_b_id=20,
            unauth_doc_id=30,
            query_vector=query_vec,
        )

        assert invariants["cross_user_ownership_enforced"] is True
        assert invariants["same_user_cross_doc_isolation_enforced"] is True
        assert invariants["valid_query_returns_data"] is True
        assert invariants["top_k_bound_respected"] is True
        assert invariants["distance_ordered_monotonically"] is True
