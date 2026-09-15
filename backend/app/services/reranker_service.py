"""Reranker service and provider abstractions (P3-05 / P3-06)."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from app.core.config import settings


@dataclass(frozen=True)
class RerankCandidate:
    """Represents a candidate chunk presented to the reranking stage."""

    chunk_id: int
    content: str
    score: float
    metadata: Optional[dict[str, Any]] = None


class BaseRerankerProvider(ABC):
    """Abstract interface for all reranker providers."""

    @abstractmethod
    def score(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[float]:
        """
        Score candidates against the given query.

        Must return a list of float scores corresponding 1:1 with candidates,
        preserving candidate sequence order.
        """
        ...


class DeterministicRerankerProvider(BaseRerankerProvider):
    """
    Deterministic reranker provider used as baseline and test fixture.

    Scores candidates using word-overlap lexical heuristic combined with original score.
    Zero DB dependencies, fully deterministic.
    """

    def score(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[float]:
        if not candidates:
            return []

        query_tokens = set(query.lower().split())
        scores: list[float] = []

        for candidate in candidates:
            if not query_tokens:
                overlap_score = 0.0
            else:
                content_tokens = set(candidate.content.lower().split())
                overlap = len(query_tokens.intersection(content_tokens))
                overlap_score = overlap / len(query_tokens)

            combined_score = 0.7 * overlap_score + 0.3 * candidate.score
            scores.append(round(combined_score, 6))

        return scores


class CrossEncoderRerankerProvider(BaseRerankerProvider):
    """
    Semantic Cross-Encoder provider utilizing sentence-transformers.

    Thread-safe lazy initialization and thread-safe CPU inference.
    Reuses model instance across worker requests.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: Optional[int] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_name = model_name or getattr(
            settings, "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        self.batch_size = batch_size or getattr(settings, "RERANKER_BATCH_SIZE", 8)
        self.device = device or getattr(settings, "RERANKER_DEVICE", "cpu")
        self._model: Any = None
        self._lock = threading.Lock()

    def _get_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(
                        self.model_name,
                        device=self.device,
                    )
        return self._model

    def score(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[float]:
        if not candidates:
            return []

        model = self._get_model()
        pairs = [[query, c.content] for c in candidates]

        with self._lock:
            raw_scores = model.predict(
                pairs,
                batch_size=self.batch_size,
            )

        scores = [float(s) for s in raw_scores]
        if len(scores) != len(candidates):
            raise ValueError(
                f"Model returned {len(scores)} scores for {len(candidates)} candidates"
            )

        return scores


_PROVIDER_CACHE: dict[str, BaseRerankerProvider] = {}
_CACHE_LOCK = threading.Lock()


def get_reranker_provider(provider_type: Optional[str] = None) -> BaseRerankerProvider:
    """
    Retrieve or initialize the process-level singleton reranker provider.
    Ensures single model instance per worker across all concurrent requests.
    """
    name = (provider_type or getattr(settings, "RERANKER_PROVIDER", "deterministic")).lower()

    if name not in _PROVIDER_CACHE:
        with _CACHE_LOCK:
            if name not in _PROVIDER_CACHE:
                if name == "cross_encoder":
                    _PROVIDER_CACHE[name] = CrossEncoderRerankerProvider()
                elif name == "deterministic":
                    _PROVIDER_CACHE[name] = DeterministicRerankerProvider()
                else:
                    raise ValueError(f"Unknown reranker provider: {name!r}")

    return _PROVIDER_CACHE[name]


def create_reranker_provider(provider_type: Optional[str] = None) -> BaseRerankerProvider:
    """Convenience alias pointing to singleton provider getter."""
    return get_reranker_provider(provider_type)


class RerankerService:
    """
    Application-level service coordinating candidate scoring and top-k truncation.
    """

    def __init__(self, provider: Optional[BaseRerankerProvider] = None) -> None:
        self.provider = provider or get_reranker_provider()

    def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
        top_k: Optional[int] = None,
    ) -> list[RerankCandidate]:
        if not candidates:
            return []
        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be a positive integer when provided")

        scores = self.provider.score(query, candidates)
        if len(scores) != len(candidates):
            raise ValueError("Provider must return exactly one score per candidate")

        scored_candidates = [
            RerankCandidate(
                chunk_id=candidate.chunk_id,
                content=candidate.content,
                score=score,
                metadata=candidate.metadata,
            )
            for candidate, score in zip(candidates, scores)
        ]

        # Sort descending by score, maintaining stable order on ties
        scored_candidates.sort(key=lambda c: c.score, reverse=True)

        if top_k is not None:
            return scored_candidates[:top_k]
        return scored_candidates
