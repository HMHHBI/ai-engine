#!/usr/bin/env python3
"""
RAG Retrieval Quality Evaluation Suite (P3-02).

Evaluates the production RAG retrieval path:

    Golden Dataset
        ↓
    EmbeddingService.generate_embedding()
        ↓
    VectorRepository.search_similar_chunks()
        ↓
    PostgreSQL + pgvector
        ↓
    Hit Rate / MRR / Context Precision / Context Recall

The evaluator is intentionally isolated from production data. It requires
TEST_DATABASE_URL and refuses to run against a non-test database.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import urlparse

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as app_session_module
from app.core.config import settings
from app.db.models import Chat, Document, DocumentChunk
from app.repositories.vector_repo import VectorRepository
from app.services.embedding_service import EmbeddingService


DEFAULT_K_VALUES = (1, 3, 5, 10)
MIN_DATASET_QUERIES = 30

DEFAULT_DATASET = Path(
    "scripts/evaluations/rag_quality_dataset.json"
)
DEFAULT_RESULTS_DIR = Path("evaluation-results")


@dataclass(frozen=True)
class EvaluationQuery:
    query_id: str
    user_id: int
    document_id: int
    query: str
    relevant_chunk_ids: frozenset[int]
    reference_answer: Optional[str] = None


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    chunk_index: Optional[int]
    content: str
    distance: float


@dataclass(frozen=True)
class QueryEvaluation:
    query_id: str
    user_id: int
    document_id: int
    query: str
    relevant_chunk_ids: tuple[int, ...]
    retrieved: tuple[RetrievedChunk, ...]
    metrics: dict[str, dict[str, float]]
    reference_answer: Optional[str] = None


def assert_test_database(url: Optional[str]) -> None:
    """Ensure evaluation runs only against an isolated test database."""
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required for RAG evaluation. "
            "Evaluation will not run without an explicit test database."
        )

    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/").split("?", 1)[0]

    if not db_name:
        raise RuntimeError(
            "TEST_DATABASE_URL does not contain a database name."
        )

    normalized_name = db_name.lower()

    if not (
        normalized_name.endswith("_test")
        or normalized_name.startswith("test_")
        or normalized_name == "test"
        or "_test_" in normalized_name
    ):
        raise RuntimeError(
            "CRITICAL SAFETY VIOLATION: Evaluation must point to a "
            f"dedicated test database, got target '{db_name}'. "
            "Aborting to prevent data contamination."
        )


def validate_k_values(k_values: Iterable[int]) -> tuple[int, ...]:
    """Validate and normalize evaluation K values."""
    values = tuple(k_values)

    if not values:
        raise ValueError("At least one K value is required.")

    if any(k <= 0 for k in values):
        raise ValueError("Every K value must be greater than zero.")

    if any(k > 50 for k in values):
        raise ValueError("Every K value must be less than or equal to 50.")

    if len(set(values)) != len(values):
        raise ValueError("K values must be unique.")

    if values != tuple(sorted(values)):
        raise ValueError("K values must be provided in ascending order.")

    return values


def _parse_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")

    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")

    return value


def load_dataset(
    path: Path,
    *,
    min_queries: int = MIN_DATASET_QUERIES,
) -> list[EvaluationQuery]:
    """Load and validate the golden retrieval dataset."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Dataset root must be a JSON object.")

    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Dataset must contain a non-empty version.")

    corpus = payload.get("corpus")
    if not isinstance(corpus, str) or not corpus.strip():
        raise ValueError("Dataset must contain a non-empty corpus.")

    raw_queries = payload.get("queries")

    if not isinstance(raw_queries, list):
        raise ValueError("Dataset must contain a 'queries' list.")

    if len(raw_queries) < min_queries:
        raise ValueError(
            f"Dataset contains {len(raw_queries)} queries. "
            f"At least {min_queries} queries are required."
        )

    parsed: list[EvaluationQuery] = []
    seen_query_ids: set[str] = set()

    for index, item in enumerate(raw_queries, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Dataset query #{index} must be a JSON object."
            )

        query_id = item.get("query_id")

        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError(
                f"Dataset query #{index} has an invalid query_id."
            )

        query_id = query_id.strip()

        if query_id in seen_query_ids:
            raise ValueError(
                f"Duplicate query_id detected: '{query_id}'."
            )

        seen_query_ids.add(query_id)

        user_id = _parse_positive_int(
            item.get("user_id"),
            f"{query_id}.user_id",
        )

        document_id = _parse_positive_int(
            item.get("document_id"),
            f"{query_id}.document_id",
        )

        query = item.get("query")

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                f"{query_id}.query must be a non-empty string."
            )

        raw_relevant_ids = item.get("relevant_chunk_ids")

        if not isinstance(raw_relevant_ids, list):
            raise ValueError(
                f"{query_id}.relevant_chunk_ids must be a list."
            )

        if not raw_relevant_ids:
            raise ValueError(
                f"{query_id}.relevant_chunk_ids cannot be empty."
            )

        relevant_ids: list[int] = []

        for chunk_id in raw_relevant_ids:
            relevant_ids.append(
                _parse_positive_int(
                    chunk_id,
                    f"{query_id}.relevant_chunk_ids",
                )
            )

        if len(set(relevant_ids)) != len(relevant_ids):
            raise ValueError(
                f"{query_id}.relevant_chunk_ids contains duplicates."
            )

        reference_answer = item.get("reference_answer")

        if reference_answer is not None:
            if not isinstance(reference_answer, str):
                raise ValueError(
                    f"{query_id}.reference_answer must be a string."
                )
            reference_answer = reference_answer.strip() or None

        parsed.append(
            EvaluationQuery(
                query_id=query_id,
                user_id=user_id,
                document_id=document_id,
                query=query.strip(),
                relevant_chunk_ids=frozenset(relevant_ids),
                reference_answer=reference_answer,
            )
        )

    return parsed


def validate_dataset_against_db(
    session: Session,
    queries: Sequence[EvaluationQuery],
) -> None:
    """
    Validate golden labels against the evaluation database.

    Every query must satisfy:

        user
          ↓
        document.user_id
          ↓
        document.chat_id
          ↓
        chat.user_id

    Every relevant chunk must belong to the specified document and have
    a stored embedding.
    """
    document_cache: dict[tuple[int, int], Document] = {}
    chunk_cache: dict[int, DocumentChunk] = {}

    for query in queries:
        cache_key = (query.user_id, query.document_id)

        if cache_key not in document_cache:
            document = session.execute(
                select(Document)
                .join(Chat, Chat.id == Document.chat_id)
                .where(
                    Document.id == query.document_id,
                    Document.user_id == query.user_id,
                    Chat.user_id == query.user_id,
                )
            ).scalar_one_or_none()

            if document is None:
                raise ValueError(
                    f"{query.query_id}: document {query.document_id} "
                    f"is not owned by user {query.user_id}."
                )

            document_cache[cache_key] = document

        document = document_cache[cache_key]

        for chunk_id in query.relevant_chunk_ids:
            if chunk_id not in chunk_cache:
                chunk = session.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.id == chunk_id,
                    )
                ).scalar_one_or_none()

                if chunk is None:
                    raise ValueError(
                        f"{query.query_id}: relevant chunk {chunk_id} "
                        "does not exist."
                    )

                chunk_cache[chunk_id] = chunk

            chunk = chunk_cache[chunk_id]

            if chunk.document_id != document.id:
                raise ValueError(
                    f"{query.query_id}: relevant chunk {chunk_id} "
                    f"belongs to document {chunk.document_id}, not "
                    f"document {document.id}."
                )

            if chunk.embedding is None:
                raise ValueError(
                    f"{query.query_id}: relevant chunk {chunk_id} "
                    "has no stored embedding."
                )


def hit_rate_at_k(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k: int,
) -> float:
    """Return binary hit rate for one query at K."""
    if k <= 0:
        return 0.0

    relevant = query.relevant_chunk_ids

    return float(
        any(
            result.chunk_id in relevant
            for result in retrieved[:k]
        )
    )


def reciprocal_rank_at_k(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k: int,
) -> float:
    """Return reciprocal rank of the first relevant result at K."""
    if k <= 0:
        return 0.0

    relevant = query.relevant_chunk_ids

    for rank, result in enumerate(retrieved[:k], start=1):
        if result.chunk_id in relevant:
            return 1.0 / rank

    return 0.0


def context_precision_at_k(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k: int,
) -> float:
    """
    Calculate precision over the chunks actually returned by retrieval.

    This intentionally uses len(top_k), rather than requested K, because
    production retrieval may return fewer than K results after adaptive
    distance filtering.
    """
    if k <= 0:
        return 0.0

    top_k = retrieved[:k]

    if not top_k:
        return 0.0

    relevant = query.relevant_chunk_ids

    hits = sum(
        1
        for result in top_k
        if result.chunk_id in relevant
    )

    return hits / len(top_k)


def context_recall_at_k(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k: int,
) -> float:
    """Calculate exact recall over canonical relevant chunk IDs."""
    if k <= 0:
        return 0.0

    relevant = query.relevant_chunk_ids

    if not relevant:
        return 0.0

    retrieved_ids = {
        result.chunk_id
        for result in retrieved[:k]
    }

    matched = retrieved_ids.intersection(relevant)

    return min(
        len(matched) / len(relevant),
        1.0,
    )


def calculate_query_metrics(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k_values: Iterable[int],
) -> dict[str, dict[str, float]]:
    """Calculate all retrieval metrics for one query."""
    metrics: dict[str, dict[str, float]] = {}

    for k in k_values:
        k_str = str(k)

        metrics[k_str] = {
            "hit_rate": hit_rate_at_k(
                retrieved,
                query,
                k,
            ),
            "mrr": reciprocal_rank_at_k(
                retrieved,
                query,
                k,
            ),
            "context_precision": context_precision_at_k(
                retrieved,
                query,
                k,
            ),
            "context_recall": context_recall_at_k(
                retrieved,
                query,
                k,
            ),
            "returned_count": float(
                len(retrieved[:k])
            ),
        }

    return metrics


def aggregate_metrics(
    evaluations: Sequence[QueryEvaluation],
    k_values: Iterable[int],
) -> dict[str, dict[str, float]]:
    """Aggregate per-query metrics using arithmetic means."""
    if not evaluations:
        raise ValueError("Cannot aggregate an empty evaluation set.")

    aggregate: dict[str, dict[str, float]] = {}

    for k in k_values:
        k_str = str(k)

        aggregate[k_str] = {
            "hit_rate": sum(
                evaluation.metrics[k_str]["hit_rate"]
                for evaluation in evaluations
            ) / len(evaluations),
            "mrr": sum(
                evaluation.metrics[k_str]["mrr"]
                for evaluation in evaluations
            ) / len(evaluations),
            "context_precision": sum(
                evaluation.metrics[k_str]["context_precision"]
                for evaluation in evaluations
            ) / len(evaluations),
            "context_recall": sum(
                evaluation.metrics[k_str]["context_recall"]
                for evaluation in evaluations
            ) / len(evaluations),
            "average_returned_count": sum(
                evaluation.metrics[k_str]["returned_count"]
                for evaluation in evaluations
            ) / len(evaluations),
        }

    return aggregate


def build_failures(
    aggregate: dict[str, dict[str, float]],
) -> list[str]:
    """
    Apply the P3-02 retrieval quality gate.

    Precision and recall remain diagnostic metrics for this phase.
    """
    failures: list[str] = []

    thresholds = {
        "1": {
            "hit_rate": 0.70,
        },
        "3": {
            "hit_rate": 0.85,
        },
        "5": {
            "hit_rate": 0.90,
            "mrr": 0.80,
        },
        "10": {
            "hit_rate": 0.95,
        },
    }

    for k, required_metrics in thresholds.items():
        if k not in aggregate:
            continue

        for metric_name, threshold in required_metrics.items():
            actual = aggregate[k].get(metric_name, 0.0)

            if actual < threshold:
                label = (
                    metric_name.upper()
                    if metric_name == "mrr"
                    else metric_name.replace("_", " ").title()
                )
                failures.append(
                    f"{label}@{k} "
                    f"({actual:.4f}) below required threshold "
                    f"{threshold:.2f}"
                )

    return failures


def serialize_evaluation(
    evaluation: QueryEvaluation,
) -> dict[str, Any]:
    """Serialize one query evaluation for JSON output."""
    return {
        "query_id": evaluation.query_id,
        "user_id": evaluation.user_id,
        "document_id": evaluation.document_id,
        "query": evaluation.query,
        "relevant_chunk_ids": list(
            evaluation.relevant_chunk_ids
        ),
        "retrieved": [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "distance": chunk.distance,
            }
            for chunk in evaluation.retrieved
        ],
        "metrics": evaluation.metrics,
        "reference_answer": evaluation.reference_answer,
    }


def write_reports(
    output_dir: Path,
    *,
    status: str,
    dataset_path: Path,
    provider: str,
    evaluations: Sequence[QueryEvaluation],
    aggregate: dict[str, dict[str, float]],
    failures: Sequence[str],
) -> tuple[Path, Path]:
    """Write machine-readable JSON and human-readable Markdown reports."""
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_dir / (
        f"rag-quality-{timestamp}.json"
    )

    md_path = output_dir / (
        f"rag-quality-{timestamp}.md"
    )

    payload = {
        "timestamp": timestamp,
        "status": status,
        "embedding_provider": provider,
        "dataset": str(dataset_path),
        "total_queries": len(evaluations),
        "aggregate": aggregate,
        "failures": list(failures),
        "queries": [
            serialize_evaluation(evaluation)
            for evaluation in evaluations
        ],
    }

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
        )

    with md_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(
            "# P3-02 RAG Retrieval Quality Evaluation\n\n"
        )

        handle.write(
            f"- Date: `{timestamp}`\n"
        )
        handle.write(
            f"- Status: **{status}**\n"
        )
        handle.write(
            f"- Embedding provider: `{provider}`\n"
        )
        handle.write(
            f"- Dataset: `{dataset_path}`\n"
        )
        handle.write(
            f"- Queries: `{len(evaluations)}`\n\n"
        )

        handle.write(
            "## Aggregate Metrics\n\n"
        )

        handle.write(
            "| K | Hit Rate | MRR | "
            "Context Precision | Context Recall | "
            "Avg Returned |\n"
        )
        handle.write(
            "|---:|---:|---:|---:|---:|---:|\n"
        )

        for k, metrics in aggregate.items():
            handle.write(
                f"| {k} | "
                f"{metrics['hit_rate']:.4f} | "
                f"{metrics['mrr']:.4f} | "
                f"{metrics['context_precision']:.4f} | "
                f"{metrics['context_recall']:.4f} | "
                f"{metrics['average_returned_count']:.2f} |\n"
            )

        handle.write("\n## Gate Failures\n\n")

        if failures:
            for failure in failures:
                handle.write(
                    f"- ❌ {failure}\n"
                )
        else:
            handle.write(
                "- None\n"
            )

        handle.write(
            "\n## Per-Query Results\n\n"
        )

        for evaluation in evaluations:
            handle.write(
                f"### {evaluation.query_id}\n\n"
            )
            handle.write(
                f"- Query: {evaluation.query}\n"
            )
            handle.write(
                f"- User ID: `{evaluation.user_id}`\n"
            )
            handle.write(
                f"- Document ID: `{evaluation.document_id}`\n"
            )
            handle.write(
                "- Relevant chunks: "
                f"{list(evaluation.relevant_chunk_ids)}\n"
            )
            handle.write(
                "- Retrieved chunks: "
                f"{[chunk.chunk_id for chunk in evaluation.retrieved]}\n\n"
            )

    return json_path, md_path


async def execute_evaluation(
    dataset_path: Path,
    output_dir: Path,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    min_queries: int = MIN_DATASET_QUERIES,
) -> dict[str, Any]:
    """Execute the complete isolated RAG retrieval evaluation."""
    k_values = validate_k_values(k_values)

    test_database_url = os.getenv("TEST_DATABASE_URL")
    assert_test_database(test_database_url)

    queries = load_dataset(
        dataset_path,
        min_queries=min_queries,
    )

    evaluation_engine = create_engine(
        test_database_url,
        connect_args={
            "options": "-c client_encoding=utf8",
        },
        pool_pre_ping=True,
    )

    EvaluationSessionLocal = sessionmaker(
        bind=evaluation_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    original_bind = app_session_module.SessionLocal.kw.get(
        "bind"
    )

    try:
        with EvaluationSessionLocal() as validation_session:
            validate_dataset_against_db(
                validation_session,
                queries,
            )

        app_session_module.SessionLocal.configure(
            bind=evaluation_engine
        )

        provider = (
            settings.DEFAULT_EMBEDDING_PROVIDER.value
        )

        print()
        print("=" * 62)
        print("  P3-02 RAG RETRIEVAL QUALITY EVALUATION")
        print("=" * 62)
        print("  Database: isolated test database")
        print(f"  Provider: {provider}")
        print(f"  Queries:  {len(queries)}")
        print(
            "  Pipeline: EmbeddingService -> "
            "VectorRepository -> pgvector"
        )
        print("=" * 62)

        evaluations: list[QueryEvaluation] = []

        for index, query in enumerate(
            queries,
            start=1,
        ):
            print(
                f"[{index}/{len(queries)}] "
                f"{query.query_id}"
            )

            query_vector = (
                await EmbeddingService.generate_embedding(
                    text=query.query,
                    model_provider=provider,
                )
            )

            if not query_vector:
                raise RuntimeError(
                    "EmbeddingService failed to generate "
                    f"an embedding for query '{query.query_id}'."
                )

            results = (
                VectorRepository.search_similar_chunks(
                    user_id=query.user_id,
                    document_id=query.document_id,
                    query_vector=query_vector,
                    top_k=max(k_values),
                )
            )

            retrieved = tuple(
                RetrievedChunk(
                    chunk_id=result["id"],
                    document_id=result["document_id"],
                    chunk_index=result.get("chunk_index"),
                    content=result.get("content", ""),
                    distance=float(
                        result.get("distance", 0.0)
                    ),
                )
                for result in results
            )

            metrics = calculate_query_metrics(
                retrieved,
                query,
                k_values,
            )

            evaluations.append(
                QueryEvaluation(
                    query_id=query.query_id,
                    user_id=query.user_id,
                    document_id=query.document_id,
                    query=query.query,
                    relevant_chunk_ids=tuple(
                        sorted(query.relevant_chunk_ids)
                    ),
                    retrieved=retrieved,
                    metrics=metrics,
                    reference_answer=query.reference_answer,
                )
            )

        aggregate = aggregate_metrics(
            evaluations,
            k_values,
        )

        failures = build_failures(
            aggregate
        )

        status = (
            "PASSED"
            if not failures
            else "FAILED"
        )

        print()
        print(
            f"{'K':<6}"
            f"{'Hit Rate':<14}"
            f"{'MRR':<14}"
            f"{'Precision':<14}"
            f"{'Recall':<14}"
        )
        print("-" * 62)

        for k in k_values:
            metrics = aggregate[str(k)]

            print(
                f"{k:<6}"
                f"{metrics['hit_rate']:<14.4f}"
                f"{metrics['mrr']:<14.4f}"
                f"{metrics['context_precision']:<14.4f}"
                f"{metrics['context_recall']:<14.4f}"
            )

        print()
        print(f"STATUS: {status}")

        for failure in failures:
            print(f"  - {failure}")

        json_path, md_path = write_reports(
            output_dir,
            status=status,
            dataset_path=dataset_path,
            provider=provider,
            evaluations=evaluations,
            aggregate=aggregate,
            failures=failures,
        )

        print()
        print("Artifacts generated:")
        print(f"  - JSON: {json_path}")
        print(f"  - Markdown: {md_path}")

        return {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": status,
            "embedding_provider": provider,
            "dataset": str(dataset_path),
            "total_queries": len(evaluations),
            "aggregate": aggregate,
            "failures": failures,
            "queries": [
                serialize_evaluation(evaluation)
                for evaluation in evaluations
            ],
        }

    finally:
        if original_bind is not None:
            app_session_module.SessionLocal.configure(
                bind=original_bind
            )

        evaluation_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate production RAG retrieval quality "
            "against an isolated test database."
        )
    )

    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to the golden evaluation dataset.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory for evaluation reports.",
    )

    parser.add_argument(
        "--min-queries",
        type=int,
        default=MIN_DATASET_QUERIES,
        help="Minimum required number of dataset queries.",
    )

    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=list(DEFAULT_K_VALUES),
        help="K values to evaluate.",
    )

    args = parser.parse_args()

    try:
        validate_k_values(args.k)

        if args.min_queries <= 0:
            raise ValueError(
                "--min-queries must be greater than zero."
            )

        queries = load_dataset(
            args.dataset,
            min_queries=args.min_queries,
        )

        if not queries:
            raise ValueError(
                "Dataset contains no evaluation queries."
            )

        asyncio.run(
            execute_evaluation(
                dataset_path=args.dataset,
                output_dir=args.output_dir,
                k_values=tuple(args.k),
                min_queries=args.min_queries,
            )
        )

    except Exception as exc:
        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
