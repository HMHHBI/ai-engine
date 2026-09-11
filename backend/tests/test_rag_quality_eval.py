from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from scripts.evaluations import rag_quality_eval as evaluator
from scripts.evaluations.rag_quality_eval import (
    EvaluationQuery,
    RetrievedChunk,
    assert_test_database,
    build_failures,
    calculate_query_metrics,
    context_precision_at_k,
    context_recall_at_k,
    hit_rate_at_k,
    reciprocal_rank_at_k,
    validate_k_values,
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
        RetrievedChunk(
            chunk_id=101,
            document_id=10,
            chunk_index=0,
            content="irrelevant",
            distance=0.10,
        ),
        RetrievedChunk(
            chunk_id=102,
            document_id=10,
            chunk_index=1,
            content="relevant",
            distance=0.12,
        ),
        RetrievedChunk(
            chunk_id=103,
            document_id=10,
            chunk_index=2,
            content="irrelevant",
            distance=0.15,
        ),
        RetrievedChunk(
            chunk_id=104,
            document_id=10,
            chunk_index=3,
            content="relevant",
            distance=0.17,
        ),
    ]


def test_safety_guardrail_blocks_non_test_db() -> None:
    with pytest.raises(
        RuntimeError,
        match="CRITICAL SAFETY VIOLATION",
    ):
        assert_test_database(
            "postgresql://postgres:pass@localhost:5432/hassan_ai_db"
        )


def test_safety_guardrail_requires_explicit_database() -> None:
    with pytest.raises(
        RuntimeError,
        match="TEST_DATABASE_URL is required",
    ):
        assert_test_database("")


def test_safety_guardrail_allows_test_db() -> None:
    assert_test_database(
        "postgresql://postgres:pass@localhost:5432/hassan_ai_test"
    )

    assert_test_database(
        "postgresql://postgres:pass@localhost:5432/test_rag"
    )

    assert_test_database(
        "postgresql://postgres:pass@localhost:5432/rag_test_corpus"
    )


def test_validate_k_values() -> None:
    assert validate_k_values(
        (1, 3, 5, 10)
    ) == (1, 3, 5, 10)


def test_validate_k_values_rejects_empty() -> None:
    with pytest.raises(
        ValueError,
        match="At least one K",
    ):
        validate_k_values(())


def test_validate_k_values_rejects_zero() -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        validate_k_values((0, 5))


def test_validate_k_values_rejects_values_above_repository_limit() -> None:
    with pytest.raises(
        ValueError,
        match="less than or equal to 50",
    ):
        validate_k_values((1, 51))


def test_validate_k_values_rejects_duplicates() -> None:
    with pytest.raises(
        ValueError,
        match="unique",
    ):
        validate_k_values((1, 3, 3, 5))


def test_validate_k_values_rejects_unsorted_values() -> None:
    with pytest.raises(
        ValueError,
        match="ascending",
    ):
        validate_k_values((5, 1, 3))


def test_hit_rate_at_k() -> None:
    query = make_query()
    results = make_results()

    assert hit_rate_at_k(
        results,
        query,
        1,
    ) == 0.0

    assert hit_rate_at_k(
        results,
        query,
        2,
    ) == 1.0


def test_reciprocal_rank_at_k() -> None:
    query = make_query()
    results = make_results()

    assert reciprocal_rank_at_k(
        results,
        query,
        1,
    ) == 0.0

    assert reciprocal_rank_at_k(
        results,
        query,
        2,
    ) == 0.5


def test_context_precision_at_k_uses_actual_returned_count() -> None:
    query = make_query()

    results = [
        RetrievedChunk(
            chunk_id=102,
            document_id=10,
            chunk_index=1,
            content="relevant",
            distance=0.12,
        ),
        RetrievedChunk(
            chunk_id=103,
            document_id=10,
            chunk_index=2,
            content="irrelevant",
            distance=0.15,
        ),
        RetrievedChunk(
            chunk_id=104,
            document_id=10,
            chunk_index=3,
            content="relevant",
            distance=0.17,
        ),
    ]

    assert context_precision_at_k(
        results,
        query,
        5,
    ) == pytest.approx(2 / 3)


def test_context_precision_at_k_empty_results() -> None:
    query = make_query()

    assert context_precision_at_k(
        [],
        query,
        5,
    ) == 0.0


def test_context_recall_at_k_exact() -> None:
    query = make_query()
    results = make_results()

    assert context_recall_at_k(
        results,
        query,
        1,
    ) == 0.0

    assert context_recall_at_k(
        results,
        query,
        2,
    ) == 0.5

    assert context_recall_at_k(
        results,
        query,
        3,
    ) == 0.5

    assert context_recall_at_k(
        results,
        query,
        4,
    ) == 1.0


def test_calculate_query_metrics() -> None:
    query = make_query()
    results = make_results()

    metrics = calculate_query_metrics(
        results,
        query,
        (1, 3, 5),
    )

    assert metrics["1"]["hit_rate"] == 0.0
    assert metrics["3"]["hit_rate"] == 1.0
    assert metrics["3"]["mrr"] == 0.5
    assert metrics["5"]["context_recall"] == 1.0
    assert metrics["5"]["returned_count"] == 4.0


def test_build_failures_accepts_passing_metrics() -> None:
    passing_aggregate = {
        "1": {
            "hit_rate": 0.75,
        },
        "3": {
            "hit_rate": 0.90,
        },
        "5": {
            "hit_rate": 0.95,
            "mrr": 0.85,
        },
        "10": {
            "hit_rate": 0.98,
        },
    }

    assert build_failures(
        passing_aggregate
    ) == []


def test_build_failures_detects_hit_rate_failure() -> None:
    aggregate = {
        "1": {
            "hit_rate": 0.50,
        },
        "3": {
            "hit_rate": 0.80,
        },
        "5": {
            "hit_rate": 0.85,
            "mrr": 0.85,
        },
        "10": {
            "hit_rate": 0.98,
        },
    }

    failures = build_failures(
        aggregate
    )

    assert len(failures) == 3
    assert any(
        "Hit Rate@1" in failure
        for failure in failures
    )
    assert any(
        "Hit Rate@3" in failure
        for failure in failures
    )
    assert any(
        "Hit Rate@5" in failure
        for failure in failures
    )


def test_build_failures_detects_mrr_failure() -> None:
    aggregate = {
        "1": {
            "hit_rate": 0.75,
        },
        "3": {
            "hit_rate": 0.90,
        },
        "5": {
            "hit_rate": 0.95,
            "mrr": 0.70,
        },
        "10": {
            "hit_rate": 0.98,
        },
    }

    failures = build_failures(
        aggregate
    )

    assert len(failures) == 1
    assert "MRR@5" in failures[0]


def test_load_dataset_rejects_duplicate_query_ids(
    tmp_path,
) -> None:
    dataset = {
        "version": "1.0",
        "corpus": "test.pdf",
        "queries": [
            {
                "query_id": "duplicate",
                "user_id": 1,
                "document_id": 1,
                "query": "first",
                "relevant_chunk_ids": [1],
            },
            {
                "query_id": "duplicate",
                "user_id": 1,
                "document_id": 1,
                "query": "second",
                "relevant_chunk_ids": [1],
            },
        ],
    }

    path = tmp_path / "dataset.json"
    path.write_text(
        __import__("json").dumps(dataset),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Duplicate query_id",
    ):
        evaluator.load_dataset(
            path,
            min_queries=1,
        )


def test_load_dataset_rejects_empty_query(
    tmp_path,
) -> None:
    dataset = {
        "version": "1.0",
        "corpus": "test.pdf",
        "queries": [
            {
                "query_id": "test-001",
                "user_id": 1,
                "document_id": 1,
                "query": "   ",
                "relevant_chunk_ids": [1],
            },
        ],
    }

    path = tmp_path / "dataset.json"
    path.write_text(
        __import__("json").dumps(dataset),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="non-empty string",
    ):
        evaluator.load_dataset(
            path,
            min_queries=1,
        )


def test_load_dataset_rejects_duplicate_relevant_chunk_ids(
    tmp_path,
) -> None:
    dataset = {
        "version": "1.0",
        "corpus": "test.pdf",
        "queries": [
            {
                "query_id": "test-001",
                "user_id": 1,
                "document_id": 1,
                "query": "test",
                "relevant_chunk_ids": [1, 1],
            },
        ],
    }

    path = tmp_path / "dataset.json"
    path.write_text(
        __import__("json").dumps(dataset),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="contains duplicates",
    ):
        evaluator.load_dataset(
            path,
            min_queries=1,
        )


def test_load_dataset_rejects_below_minimum(
    tmp_path,
) -> None:
    dataset = {
        "version": "1.0",
        "corpus": "test.pdf",
        "queries": [
            {
                "query_id": "test-001",
                "user_id": 1,
                "document_id": 1,
                "query": "test",
                "relevant_chunk_ids": [1],
            },
        ],
    }

    path = tmp_path / "dataset.json"
    path.write_text(
        __import__("json").dumps(dataset),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="At least 30 queries",
    ):
        evaluator.load_dataset(path)


@pytest.mark.asyncio
async def test_production_embedding_and_retrieval_boundary(
    monkeypatch,
) -> None:
    query = make_query()

    embedding_mock = AsyncMock(
        return_value=[0.1, 0.2, 0.3]
    )

    retrieval_calls = []

    def fake_retrieval(**kwargs):
        retrieval_calls.append(kwargs)
        return [
            {
                "id": 102,
                "document_id": 10,
                "chat_id": 20,
                "content": "relevant",
                "chunk_index": 1,
                "distance": 0.12,
            }
        ]

    monkeypatch.setattr(
        evaluator.EmbeddingService,
        "generate_embedding",
        embedding_mock,
    )

    monkeypatch.setattr(
        evaluator.VectorRepository,
        "search_similar_chunks",
        fake_retrieval,
    )

    provider = "ollama"

    query_vector = await evaluator.EmbeddingService.generate_embedding(
        text=query.query,
        model_provider=provider,
    )

    results = evaluator.VectorRepository.search_similar_chunks(
        user_id=query.user_id,
        document_id=query.document_id,
        query_vector=query_vector,
        top_k=10,
    )

    embedding_mock.assert_awaited_once_with(
        text="test query",
        model_provider="ollama",
    )

    assert len(retrieval_calls) == 1
    assert retrieval_calls[0]["user_id"] == 1
    assert retrieval_calls[0]["document_id"] == 10
    assert retrieval_calls[0]["query_vector"] == [
        0.1,
        0.2,
        0.3,
    ]
    assert retrieval_calls[0]["top_k"] == 10

    assert results[0]["id"] == 102


def test_dataset_validation_rejects_foreign_chunk(
    monkeypatch,
) -> None:
    query = make_query()

    class FakeSession:
        def execute(self, statement):
            class Result:
                def scalar_one_or_none(self):
                    class FakeDocument:
                        id = 10

                    return FakeDocument()

            return Result()

    session = FakeSession()

    calls = []

    original_execute = session.execute

    def execute(statement):
        calls.append(statement)

        class Result:
            def scalar_one_or_none(self):
                if len(calls) == 1:
                    class FakeDocument:
                        id = 10

                    return FakeDocument()

                class FakeChunk:
                    id = 102
                    document_id = 99
                    embedding = [0.1]

                return FakeChunk()

        return Result()

    monkeypatch.setattr(
        session,
        "execute",
        execute,
    )

    with pytest.raises(
        ValueError,
        match="belongs to document 99",
    ):
        evaluator.validate_dataset_against_db(
            session,
            [query],
        )
