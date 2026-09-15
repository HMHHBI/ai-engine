"""Unit tests for the deterministic RAG reranking service."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.services.reranker_service import (
    BaseRerankerProvider,
    DeterministicRerankerProvider,
    RerankCandidate,
    RerankerService,
)


def _candidate(
    chunk_id: int,
    content: str,
    score: float = 0.0,
    metadata: dict | None = None,
) -> RerankCandidate:
    """Build a test candidate with optional metadata."""
    return RerankCandidate(
        chunk_id=chunk_id,
        content=content,
        score=score,
        metadata=metadata,
    )


class FixedProvider(BaseRerankerProvider):
    """Provider returning predefined scores for service-level tests."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def score(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[float]:
        return self.scores


class RecordingProvider(BaseRerankerProvider):
    """Provider used to verify service/provider interaction."""

    def __init__(self) -> None:
        self.query: str | None = None
        self.candidates: list[RerankCandidate] | None = None

    def score(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[float]:
        self.query = query
        self.candidates = list(candidates)
        return [float(index) for index in range(len(candidates))]


def test_rerank_orders_candidates_by_score() -> None:
    """Candidates are returned from highest to lowest provider score."""
    candidates = [
        _candidate(1, "first"),
        _candidate(2, "second"),
        _candidate(3, "third"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.20, 0.90, 0.50])
    )

    result = service.rerank("query", candidates)

    assert [candidate.chunk_id for candidate in result] == [2, 3, 1]
    assert [candidate.score for candidate in result] == [0.90, 0.50, 0.20]


def test_rerank_applies_top_k_after_scoring() -> None:
    """top_k limits the final ranked result rather than the input pool."""
    candidates = [
        _candidate(1, "one"),
        _candidate(2, "two"),
        _candidate(3, "three"),
        _candidate(4, "four"),
        _candidate(5, "five"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.10, 0.80, 0.50, 0.95, 0.30])
    )

    result = service.rerank("query", candidates, top_k=3)

    assert [candidate.chunk_id for candidate in result] == [4, 2, 3]
    assert len(result) == 3


def test_rerank_without_top_k_returns_all_candidates() -> None:
    """When top_k is omitted, every candidate is returned."""
    candidates = [
        _candidate(1, "one"),
        _candidate(2, "two"),
        _candidate(3, "three"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.10, 0.30, 0.20])
    )

    result = service.rerank("query", candidates)

    assert [candidate.chunk_id for candidate in result] == [2, 3, 1]


def test_rerank_is_deterministic() -> None:
    """Repeated scoring of the same input produces identical results."""
    candidates = [
        _candidate(1, "PostgreSQL connection pool configuration"),
        _candidate(2, "Redis cache configuration"),
        _candidate(3, "PostgreSQL and Redis operations"),
        _candidate(4, "Unrelated deployment documentation"),
    ]

    service = RerankerService()

    first = service.rerank(
        "PostgreSQL Redis configuration",
        candidates,
        top_k=3,
    )
    second = service.rerank(
        "PostgreSQL Redis configuration",
        candidates,
        top_k=3,
    )

    assert first == second


def test_equal_scores_preserve_original_candidate_order() -> None:
    """Ties are resolved using the original candidate ordering."""
    candidates = [
        _candidate(10, "candidate one"),
        _candidate(20, "candidate two"),
        _candidate(30, "candidate three"),
    ]

    service = RerankerService(
        provider=FixedProvider([1.0, 1.0, 1.0])
    )

    result = service.rerank("query", candidates)

    assert [candidate.chunk_id for candidate in result] == [10, 20, 30]


def test_empty_candidates_return_empty_result() -> None:
    """An empty candidate pool does not invoke scoring logic."""
    provider = RecordingProvider()
    service = RerankerService(provider=provider)

    result = service.rerank("query", [])

    assert result == []
    assert provider.query is None
    assert provider.candidates is None


def test_top_k_larger_than_candidate_count_returns_all() -> None:
    """top_k larger than the pool does not create artificial candidates."""
    candidates = [
        _candidate(1, "one"),
        _candidate(2, "two"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.5, 0.8])
    )

    result = service.rerank("query", candidates, top_k=10)

    assert [candidate.chunk_id for candidate in result] == [2, 1]


def test_top_k_one_returns_single_best_candidate() -> None:
    """top_k=1 returns exactly the highest-scoring candidate."""
    candidates = [
        _candidate(1, "one"),
        _candidate(2, "two"),
        _candidate(3, "three"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.1, 0.9, 0.3])
    )

    result = service.rerank("query", candidates, top_k=1)

    assert len(result) == 1
    assert result[0].chunk_id == 2


@pytest.mark.parametrize("top_k", [0, -1, -10])
def test_invalid_top_k_raises_value_error(top_k: int) -> None:
    """Non-positive top_k values are rejected explicitly."""
    candidates = [_candidate(1, "candidate")]

    service = RerankerService(
        provider=FixedProvider([1.0])
    )

    with pytest.raises(ValueError, match="top_k"):
        service.rerank("query", candidates, top_k=top_k)


def test_provider_receives_query_and_original_candidates() -> None:
    """The service passes the original query and candidate pool to provider."""
    candidates = [
        _candidate(
            1,
            "first",
            score=0.25,
            metadata={"document_id": 100},
        ),
        _candidate(
            2,
            "second",
            score=0.50,
            metadata={"document_id": 100},
        ),
    ]

    provider = RecordingProvider()
    service = RerankerService(provider=provider)

    service.rerank("specific query", candidates)

    assert provider.query == "specific query"
    assert provider.candidates == candidates


def test_metadata_is_preserved() -> None:
    """Candidate metadata survives reranking unchanged."""
    metadata_one = {
        "document_id": 101,
        "chunk_index": 4,
        "source": "manual.pdf",
    }
    metadata_two = {
        "document_id": 101,
        "chunk_index": 8,
        "source": "manual.pdf",
    }

    candidates = [
        _candidate(1, "first", metadata=metadata_one),
        _candidate(2, "second", metadata=metadata_two),
    ]

    service = RerankerService(
        provider=FixedProvider([0.2, 0.9])
    )

    result = service.rerank("query", candidates)

    assert result[0].chunk_id == 2
    assert result[0].metadata == metadata_two

    assert result[1].chunk_id == 1
    assert result[1].metadata == metadata_one


def test_original_candidate_objects_are_not_mutated() -> None:
    """Reranking creates scored candidates instead of mutating inputs."""
    candidates = [
        _candidate(1, "first", score=0.10),
        _candidate(2, "second", score=0.20),
    ]

    original = list(candidates)

    service = RerankerService(
        provider=FixedProvider([0.8, 0.9])
    )

    result = service.rerank("query", candidates)

    assert candidates == original
    assert result[0] is not candidates[1]
    assert result[1] is not candidates[0]

    assert candidates[0].score == 0.10
    assert candidates[1].score == 0.20


def test_rerank_candidate_is_frozen() -> None:
    """RerankCandidate is immutable."""
    candidate = _candidate(1, "content")

    with pytest.raises(FrozenInstanceError):
        candidate.chunk_id = 999  # type: ignore[misc]


def test_provider_score_count_must_match_candidates() -> None:
    """Invalid provider output is rejected instead of silently truncating."""
    candidates = [
        _candidate(1, "one"),
        _candidate(2, "two"),
    ]

    service = RerankerService(
        provider=FixedProvider([0.5])
    )

    with pytest.raises(
        ValueError,
        match="exactly one score per candidate",
    ):
        service.rerank("query", candidates)


def test_default_service_uses_deterministic_provider() -> None:
    """The default service is backed by the deterministic provider."""
    service = RerankerService()

    assert isinstance(
        service.provider,
        DeterministicRerankerProvider,
    )


def test_deterministic_provider_empty_candidates() -> None:
    """The provider handles an empty candidate sequence."""
    provider = DeterministicRerankerProvider()

    assert provider.score("query", []) == []


def test_deterministic_provider_empty_query_returns_zero_scores() -> None:
    """An empty query produces neutral scores."""
    candidates = [
        _candidate(1, "PostgreSQL documentation"),
        _candidate(2, "Redis documentation"),
    ]

    provider = DeterministicRerankerProvider()

    scores = provider.score("", candidates)

    assert scores == [0.0, 0.0]


def test_deterministic_provider_prefers_query_overlap() -> None:
    """Candidates matching more query terms receive higher scores."""
    candidates = [
        _candidate(
            1,
            "PostgreSQL connection pooling configuration",
        ),
        _candidate(
            2,
            "Frontend deployment configuration",
        ),
    ]

    provider = DeterministicRerankerProvider()

    scores = provider.score(
        "PostgreSQL connection pooling",
        candidates,
    )

    assert scores[0] > scores[1]


def test_deterministic_provider_exact_phrase_gets_bonus() -> None:
    """An exact normalized query phrase increases relevance."""
    candidates = [
        _candidate(
            1,
            "The PostgreSQL connection pool is configured here.",
        ),
        _candidate(
            2,
            "The PostgreSQL pool configuration is documented here.",
        ),
    ]

    provider = DeterministicRerankerProvider()

    scores = provider.score(
        "PostgreSQL connection pool",
        candidates,
    )

    assert scores[0] > scores[1]


def test_identifier_tokens_are_preserved() -> None:
    """Important technical identifiers participate in scoring."""
    candidates = [
        _candidate(
            1,
            "Incident INC-4821 was caused by X-Request-ID handling.",
        ),
        _candidate(
            2,
            "General incident response procedures.",
        ),
    ]

    provider = DeterministicRerankerProvider()

    scores = provider.score(
        "INC-4821 X-Request-ID",
        candidates,
    )

    assert scores[0] > scores[1]


def test_candidate_content_is_not_modified() -> None:
    """The reranker never changes candidate content."""
    content = "Original PostgreSQL content."

    candidate = _candidate(
        42,
        content,
        metadata={"document_id": 7},
    )

    result = RerankerService().rerank(
        "PostgreSQL",
        [candidate],
    )

    assert result[0].content == content
    assert result[0].metadata == {"document_id": 7}


def test_negative_provider_scores_are_supported() -> None:
    """Provider scores are treated as generic numeric relevance scores."""
    candidates = [
        _candidate(1, "first"),
        _candidate(2, "second"),
    ]

    service = RerankerService(
        provider=FixedProvider([-0.5, -0.1])
    )

    result = service.rerank("query", candidates)

    assert [candidate.chunk_id for candidate in result] == [2, 1]
    assert result[0].score == -0.1
    assert result[1].score == -0.5


# ----------------------------------------------------------------------
# Cross-Encoder Provider Tests (Mocked)
# ----------------------------------------------------------------------
from unittest.mock import MagicMock, patch
import pytest
from app.services.reranker_service import (
    CrossEncoderRerankerProvider,
    DeterministicRerankerProvider,
    create_reranker_provider,
)


def test_cross_encoder_lazy_loading() -> None:
    provider = CrossEncoderRerankerProvider(
        model_name="test-model",
        device="cpu",
    )
    assert provider._model is None

    mock_model = MagicMock()
    mock_model.predict.return_value = [0.85]
    mock_cross_encoder_cls = MagicMock(return_value=mock_model)
    mock_st_module = MagicMock(CrossEncoder=mock_cross_encoder_cls)

    with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
        candidates = [_candidate(1, "chunk one")]
        scores = provider.score("query", candidates)

        assert scores == [0.85]
        mock_cross_encoder_cls.assert_called_once_with("test-model", device="cpu")
        assert provider._model is mock_model

        # Second call should reuse instance without re-instantiating
        provider.score("query 2", candidates)
        assert mock_cross_encoder_cls.call_count == 1


def test_cross_encoder_empty_candidates_skips_model_load() -> None:
    provider = CrossEncoderRerankerProvider()
    mock_cross_encoder_cls = MagicMock()
    mock_st_module = MagicMock(CrossEncoder=mock_cross_encoder_cls)

    with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
        scores = provider.score("query", [])
        assert scores == []
        mock_cross_encoder_cls.assert_not_called()
    assert provider._model is None


def test_cross_encoder_pair_construction_and_batch_size() -> None:
    provider = CrossEncoderRerankerProvider(batch_size=16)
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9, 0.5]
    provider._model = mock_model

    candidates = [
        _candidate(1, "chunk A"),
        _candidate(2, "chunk B"),
        _candidate(3, "chunk C"),
    ]

    scores = provider.score("test query", candidates)

    assert scores == [0.1, 0.9, 0.5]
    mock_model.predict.assert_called_once_with(
        [
            ["test query", "chunk A"],
            ["test query", "chunk B"],
            ["test query", "chunk C"],
        ],
        batch_size=16,
    )


def test_cross_encoder_score_length_mismatch_raises_value_error() -> None:
    provider = CrossEncoderRerankerProvider()
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5]  # 1 score for 2 candidates
    provider._model = mock_model

    candidates = [_candidate(1, "A"), _candidate(2, "B")]

    with pytest.raises(ValueError, match="Model returned 1 scores for 2 candidates"):
        provider.score("query", candidates)


def test_cross_encoder_via_reranker_service_ordering_and_metadata() -> None:
    provider = CrossEncoderRerankerProvider()
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.10, 0.90, 0.50]
    provider._model = mock_model

    service = RerankerService(provider=provider)
    candidates = [
        _candidate(101, "Candidate 1", metadata={"page": 1}),
        _candidate(102, "Candidate 2", metadata={"page": 2}),
        _candidate(103, "Candidate 3", metadata={"page": 3}),
    ]

    ranked = service.rerank("my query", candidates, top_k=2)

    assert len(ranked) == 2
    assert ranked[0].chunk_id == 102
    assert ranked[0].score == 0.90
    assert ranked[0].metadata == {"page": 2}

    assert ranked[1].chunk_id == 103
    assert ranked[1].score == 0.50
    assert ranked[1].metadata == {"page": 3}


def test_create_reranker_provider_factory() -> None:
    deterministic = create_reranker_provider("deterministic")
    assert isinstance(deterministic, DeterministicRerankerProvider)

    cross_encoder = create_reranker_provider("cross_encoder")
    assert isinstance(cross_encoder, CrossEncoderRerankerProvider)

    with pytest.raises(ValueError, match="Unknown reranker provider"):
        create_reranker_provider("invalid_provider")
