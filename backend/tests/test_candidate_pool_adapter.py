"""Unit tests for VectorRepository.retrieve_candidate_pool."""

import pytest
from unittest.mock import patch
from app.repositories.vector_repo import VectorRepository


def test_retrieve_candidate_pool_validates_candidate_k():
    with pytest.raises(ValueError, match="candidate_k must be between 1 and 50"):
        VectorRepository.retrieve_candidate_pool(
            user_id=1,
            document_id=1,
            strategy="dense",
            query_text="test",
            query_vector=[0.1] * 768,
            candidate_k=0,
        )
    with pytest.raises(ValueError, match="candidate_k must be between 1 and 50"):
        VectorRepository.retrieve_candidate_pool(
            user_id=1,
            document_id=1,
            strategy="dense",
            query_text="test",
            query_vector=[0.1] * 768,
            candidate_k=51,
        )


def test_retrieve_candidate_pool_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="Unsupported retrieval strategy"):
        VectorRepository.retrieve_candidate_pool(
            user_id=1,
            document_id=1,
            strategy="unknown_strategy",
            query_text="test",
            query_vector=[0.1] * 768,
            candidate_k=20,
        )


@patch.object(VectorRepository, "search_similar_chunks")
def test_retrieve_candidate_pool_routes_dense(mock_dense):
    mock_dense.return_value = [{"chunk_id": 1}]
    vec = [0.1] * 768
    res = VectorRepository.retrieve_candidate_pool(
        user_id=10,
        document_id=20,
        strategy="dense",
        query_text="query",
        query_vector=vec,
        candidate_k=15,
    )
    assert res == [{"chunk_id": 1}]
    mock_dense.assert_called_once_with(
        user_id=10,
        document_id=20,
        query_vector=vec,
        top_k=15,
        max_distance=0.70,
        adaptive_margin=0.15,
    )


@patch.object(VectorRepository, "search_sparse_chunks")
def test_retrieve_candidate_pool_routes_lexical(mock_sparse):
    mock_sparse.return_value = [{"chunk_id": 2}]
    res = VectorRepository.retrieve_candidate_pool(
        user_id=10,
        document_id=20,
        strategy="lexical",
        query_text="query",
        query_vector=[0.1] * 768,
        candidate_k=20,
    )
    assert res == [{"chunk_id": 2}]
    mock_sparse.assert_called_once_with(
        user_id=10,
        document_id=20,
        query_text="query",
        top_k=20,
    )


@patch.object(VectorRepository, "search_hybrid_chunks")
def test_retrieve_candidate_pool_routes_hybrid(mock_hybrid):
    mock_hybrid.return_value = [{"chunk_id": 3}]
    vec = [0.1] * 768
    res = VectorRepository.retrieve_candidate_pool(
        user_id=10,
        document_id=20,
        strategy="hybrid",
        query_text="query",
        query_vector=vec,
        candidate_k=20,
    )
    assert res == [{"chunk_id": 3}]
    mock_hybrid.assert_called_once_with(
        user_id=10,
        document_id=20,
        query_text="query",
        query_vector=vec,
        top_k=20,
        candidate_k=20,
        rrf_k=60,
        dense_weight=1.0,
        sparse_weight=1.0,
        max_distance=0.70,
        adaptive_margin=0.15,
    )
