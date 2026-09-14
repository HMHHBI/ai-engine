"""
Deterministic reranking service for RAG candidate pools.

This module intentionally contains no database or repository dependencies.
The reranker receives an already-authorized candidate pool and returns the
highest-scoring candidates while preserving their original metadata.

The deterministic provider is suitable for evaluation, regression testing,
and development. It is not a neural cross-encoder and should not be treated
as a production-quality semantic reranker.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./:-]+")


@dataclass(frozen=True)
class RerankCandidate:
    """Immutable candidate passed through the reranking pipeline."""

    chunk_id: int
    content: str
    score: float = 0.0
    metadata: Mapping[str, Any] | None = None


class BaseRerankerProvider(ABC):
    """Interface implemented by reranking providers."""

    @abstractmethod
    def score(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> Sequence[float]:
        """
        Return one relevance score for every candidate.

        Implementations must preserve candidate ordering in the returned
        scores and must return exactly one score per candidate.
        """
        raise NotImplementedError


class DeterministicRerankerProvider(BaseRerankerProvider):
    """
    Deterministic lexical relevance scorer.

    The scorer combines:
    - query-token coverage,
    - candidate-token coverage,
    - exact phrase matching,
    - exact token frequency.

    This provides stable ordering without requiring a model download,
    external service, GPU, or additional runtime dependency.

    It is intentionally named "DeterministicRerankerProvider" rather than
    "CrossEncoderRerankerProvider": this implementation is not a neural
    cross-encoder.
    """

    def score(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> Sequence[float]:
        """Score candidates deterministically against the supplied query."""
        if not candidates:
            return []

        query_tokens = self._tokenize(query)

        if not query_tokens:
            return [0.0] * len(candidates)

        query_token_set = set(query_tokens)

        scores: list[float] = []

        for candidate in candidates:
            candidate_tokens = self._tokenize(candidate.content)

            if not candidate_tokens:
                scores.append(0.0)
                continue

            candidate_token_set = set(candidate_tokens)

            matched_tokens = query_token_set & candidate_token_set

            query_coverage = len(matched_tokens) / len(query_token_set)

            candidate_coverage = len(matched_tokens) / len(
                candidate_token_set
            )

            phrase_bonus = self._phrase_bonus(
                query=query,
                content=candidate.content,
            )

            frequency_score = self._frequency_score(
                query_tokens=query_tokens,
                candidate_tokens=candidate_tokens,
            )

            score = (
                query_coverage * 0.50
                + candidate_coverage * 0.20
                + frequency_score * 0.20
                + phrase_bonus * 0.10
            )

            scores.append(score)

        return scores

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text while preserving useful identifier characters."""
        return [
            token.lower()
            for token in _TOKEN_PATTERN.findall(text)
            if token.strip()
        ]

    @staticmethod
    def _phrase_bonus(query: str, content: str) -> float:
        """Return a binary bonus when the normalized query is present."""
        normalized_query = " ".join(query.lower().split())
        normalized_content = " ".join(content.lower().split())

        if not normalized_query:
            return 0.0

        return 1.0 if normalized_query in normalized_content else 0.0

    @staticmethod
    def _frequency_score(
        query_tokens: Sequence[str],
        candidate_tokens: Sequence[str],
    ) -> float:
        """
        Measure how frequently query terms occur in the candidate.

        The value is capped at 1.0 to keep frequency from dominating
        the other relevance signals.
        """
        if not query_tokens or not candidate_tokens:
            return 0.0

        candidate_text = " ".join(candidate_tokens)

        matched_frequency = sum(
            candidate_text.split().count(token)
            for token in set(query_tokens)
        )

        denominator = max(len(query_tokens), 1)

        return min(matched_frequency / denominator, 1.0)


class RerankerService:
    """
    Application-level reranking service.

    The service is intentionally stateless. It does not retrieve candidates,
    enforce tenant authorization, or access the database. Those concerns
    remain with the retrieval layer.

    The service guarantees:
    - empty input remains empty,
    - candidate metadata is preserved,
    - candidate identity is preserved,
    - deterministic providers produce deterministic ordering,
    - top_k is applied after scoring,
    - ties are resolved deterministically by original candidate position.
    """

    def __init__(
        self,
        provider: BaseRerankerProvider | None = None,
    ) -> None:
        """Initialize the service with the supplied reranker provider."""
        self.provider = provider or DeterministicRerankerProvider()

    def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_k: int | None = None,
    ) -> list[RerankCandidate]:
        """
        Rerank candidates and optionally return only the top ``top_k``.

        Args:
            query: User query used for relevance scoring.
            candidates: Already-authorized retrieval candidates.
            top_k: Maximum number of candidates to return.

        Returns:
            Candidates ordered from highest to lowest reranker score.

        Raises:
            ValueError: If ``top_k`` is less than one or the provider returns
                an invalid number of scores.
        """
        candidate_list = list(candidates)

        if not candidate_list:
            return []

        if top_k is not None and top_k < 1:
            raise ValueError("top_k must be greater than zero")

        scores = list(self.provider.score(query, candidate_list))

        if len(scores) != len(candidate_list):
            raise ValueError(
                "Reranker provider must return exactly one score per "
                "candidate"
            )

        scored_candidates = [
            (
                index,
                RerankCandidate(
                    chunk_id=candidate.chunk_id,
                    content=candidate.content,
                    score=float(score),
                    metadata=candidate.metadata,
                ),
            )
            for index, (candidate, score) in enumerate(
                zip(candidate_list, scores)
            )
        ]

        scored_candidates.sort(
            key=lambda item: (-item[1].score, item[0])
        )

        ranked = [candidate for _, candidate in scored_candidates]

        if top_k is not None:
            return ranked[:top_k]

        return ranked
