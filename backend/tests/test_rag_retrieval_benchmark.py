import pytest
from unittest.mock import MagicMock, patch
from scripts.benchmarks.rag_retrieval_benchmark import (
    generate_synthetic_unit_vector,
    verify_retrieval_isolation_and_invariants,
)

def test_generate_synthetic_unit_vector():
    vec = generate_synthetic_unit_vector(768)
    assert len(vec) == 768
    # Norm should be approximately 1.0
    norm = sum(x * x for x in vec) ** 0.5
    assert 0.99 <= norm <= 1.01

def test_verify_retrieval_isolation_mocked():
    query_vec = [0.1] * 768

    def mock_search(user_id, document_id, query_vector, top_k=6, **kwargs):
        if user_id == 1 and document_id == 10:
            return [
                {"id": 1, "distance": 0.1},
                {"id": 2, "distance": 0.15},
                {"id": 3, "distance": 0.2},
            ]
        # Cross-user or cross-document returns empty
        return []

    with patch("app.repositories.vector_repo.VectorRepository.search_similar_chunks", side_effect=mock_search):
        invariants = verify_retrieval_isolation_and_invariants(
            owner_id=1,
            unauth_id=2,
            owner_doc_id=10,
            unauth_doc_id=20,
            query_vector=query_vec,
        )

        assert invariants["cross_user_isolation_enforced"] is True
        assert invariants["cross_doc_isolation_enforced"] is True
        assert invariants["valid_query_returns_data"] is True
        assert invariants["top_k_bound_respected"] is True
        assert invariants["distance_ordered_monotonically"] is True
