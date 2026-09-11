#!/usr/bin/env python3
"""
RAG Retrieval Quality Evaluation Suite (P3-02)

Evaluates the production pgvector retrieval pipeline:
    Evaluation Runner
        ↓
    EmbeddingService.generate_embedding()
        ↓
    VectorRepository.search_similar_chunks()
        ↓
    pgvector cosine similarity
        ↓
    Hit Rate / MRR / Context Precision / Context Recall
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Set
from urllib.parse import urlparse

from sqlalchemy import create_engine

# Production application components
import app.db.session as app_session_module
from app.repositories.vector_repo import VectorRepository
from app.services.embedding_service import EmbeddingService

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:mysecretpassword@db:5432/hassan_ai_test",
)


def assert_test_database(url: str) -> None:
    """Ensure evaluation runs strictly against isolated test DB."""
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/")
    if not (db_name.endswith("_test") or "test" in db_name.lower()):
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Evaluation must point to a dedicated test database, "
            f"got target: '{db_name}'. Aborting to prevent data contamination."
        )


@dataclass(frozen=True)
class EvaluationQuery:
    query_id: str
    user_id: int
    document_id: int
    query: str
    relevant_chunk_ids: Any
    reference_answer: Optional[str] = None

    def get_relevant_ids(self) -> set[int]:
        return set(self.relevant_chunk_ids)


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    distance: float


def hit_rate_at_k(retrieved: Sequence[RetrievedChunk], query: EvaluationQuery, k: int) -> float:
    relevant = query.get_relevant_ids()
    top_k = retrieved[:k]
    return 1.0 if any(r.chunk_id in relevant for r in top_k) else 0.0


def reciprocal_rank_at_k(retrieved: Sequence[RetrievedChunk], query: EvaluationQuery, k: int) -> float:
    relevant = query.get_relevant_ids()
    for rank, item in enumerate(retrieved[:k], start=1):
        if item.chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def context_precision_at_k(retrieved: Sequence[RetrievedChunk], query: EvaluationQuery, k: int) -> float:
    if k <= 0:
        return 0.0
    relevant = query.get_relevant_ids()
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r.chunk_id in relevant)
    return hits / k


def context_recall_at_k(retrieved: Sequence[RetrievedChunk], query: EvaluationQuery, k: int) -> float:
    relevant = query.get_relevant_ids()
    if not relevant:
        return 0.0
    top_k = retrieved[:k]
    retrieved_ids = {r.chunk_id for r in top_k}
    hits = len(retrieved_ids.intersection(relevant))
    return hits / len(relevant)


def calculate_query_metrics(
    retrieved: Sequence[RetrievedChunk],
    query: EvaluationQuery,
    k_values: Iterable[int],
) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for k in k_values:
        k_str = str(k)
        metrics[k_str] = {
            "hit_rate": hit_rate_at_k(retrieved, query, k),
            "mrr": reciprocal_rank_at_k(retrieved, query, k),
            "context_precision": context_precision_at_k(retrieved, query, k),
            "context_recall": context_recall_at_k(retrieved, query, k),
        }
    return metrics


def build_failures(aggregate_metrics: dict[str, dict[str, float]]) -> list[str]:
    failures: list[str] = []
    k5_hit_rate = aggregate_metrics.get("5", {}).get("hit_rate", 0.0)
    k5_mrr = aggregate_metrics.get("5", {}).get("mrr", 0.0)

    if k5_hit_rate < 0.80:
        failures.append(f"Hit Rate@5 ({k5_hit_rate:.4f}) below required threshold 0.80")
    if k5_mrr < 0.60:
        failures.append(f"MRR@5 ({k5_mrr:.4f}) below required threshold 0.60")

    return failures


async def execute_evaluation(
    dataset_path: Path,
    output_dir: Path,
    k_values: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, Any]:
    assert_test_database(TEST_DB_URL)

    # Bind application session scope directly to test database
    test_engine = create_engine(TEST_DB_URL)
    app_session_module.SessionLocal.configure(bind=test_engine)

    with open(dataset_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    queries = [
        EvaluationQuery(
            query_id=q["query_id"],
            user_id=q["user_id"],
            document_id=q["document_id"],
            query=q["query"],
            relevant_chunk_ids=q["relevant_chunk_ids"],
            reference_answer=q.get("reference_answer"),
        )
        for q in raw_data["queries"]
    ]

    max_k = max(k_values)
    all_retrievals: dict[str, list[RetrievedChunk]] = {}

    print("\n==================================================")
    print("  P3-02 RAG RETRIEVAL QUALITY EVALUATION")
    print("  Target: hassan_ai_test")
    print("  Pipeline: EmbeddingService -> VectorRepository")
    print("==================================================")

    for eq in queries:
        # Step 1: Real query embedding via production service
        query_vector = await EmbeddingService.generate_embedding(eq.query, "gemini")
        if not query_vector:
            raise RuntimeError(f"EmbeddingService failed to generate embedding for query: {eq.query}")

        # Step 2: Retrieval via production VectorRepository
        results = VectorRepository.search_similar_chunks(
            user_id=eq.user_id,
            document_id=eq.document_id,
            query_vector=query_vector,
            top_k=max_k,
            max_distance=1.0,
            adaptive_margin=1.0,
        )

        all_retrievals[eq.query_id] = [
            RetrievedChunk(
                chunk_id=r["id"],
                document_id=r["document_id"],
                chunk_index=r["chunk_index"],
                content=r.get("content", ""),
                distance=r.get("distance", 0.0),
            )
            for r in results
        ]

    # Aggregate metrics
    aggregate: dict[str, dict[str, float]] = {}
    for k in k_values:
        k_str = str(k)
        hit_rates = []
        mrrs = []
        precisions = []
        recalls = []

        for eq in queries:
            retrieved = all_retrievals[eq.query_id]
            hit_rates.append(hit_rate_at_k(retrieved, eq, k))
            mrrs.append(reciprocal_rank_at_k(retrieved, eq, k))
            precisions.append(context_precision_at_k(retrieved, eq, k))
            recalls.append(context_recall_at_k(retrieved, eq, k))

        aggregate[k_str] = {
            "hit_rate": sum(hit_rates) / len(hit_rates),
            "mrr": sum(mrrs) / len(mrrs),
            "context_precision": sum(precisions) / len(precisions),
            "context_recall": sum(recalls) / len(recalls),
        }

    print(f"{'K':<6}{'Hit Rate':<14}{'MRR':<14}{'Precision':<14}{'Recall':<14}")
    print("-" * 62)
    for k in k_values:
        k_str = str(k)
        m = aggregate[k_str]
        print(f"{k:<6}{m['hit_rate']:<14.4f}{m['mrr']:<14.4f}{m['context_precision']:<14.4f}{m['context_recall']:<14.4f}")

    failures = build_failures(aggregate)
    status = "PASSED" if not failures else "FAILED"
    print(f"\nSTATUS: {status}")
    if failures:
        for f_msg in failures:
            print(f"  - {f_msg}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"rag-quality-{timestamp}.json"
    md_path = output_dir / f"rag-quality-{timestamp}.md"

    summary_payload = {
        "timestamp": timestamp,
        "status": status,
        "target_db": "hassan_ai_test",
        "dataset": str(dataset_path),
        "total_queries": len(queries),
        "aggregate": aggregate,
        "failures": failures,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# RAG Retrieval Quality Evaluation Report\n\n")
        f.write(f"- Date: {timestamp}\n")
        f.write("- Target DB: `hassan_ai_test`\n")
        f.write(f"- Status: **{status}**\n\n")
        f.write("| K | Hit Rate | MRR | Precision | Recall |\n")
        f.write("|---|---|---|---|---|\n")
        for k in k_values:
            m = aggregate[str(k)]
            f.write(f"| {k} | {m['hit_rate']:.4f} | {m['mrr']:.4f} | {m['context_precision']:.4f} | {m['context_recall']:.4f} |\n")

    print(f"Artifacts generated:\n  - JSON: {json_path}\n  - Markdown: {md_path}")
    return summary_payload


def main():
    parser = argparse.ArgumentParser(description="Evaluate production RAG retrieval quality.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("scripts/evaluations/rag_quality_dataset.json"),
        help="Path to golden evaluation dataset",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation-results"),
        help="Directory to save evaluation artifacts",
    )
    args = parser.parse_args()

    try:
        asyncio.run(execute_evaluation(args.dataset, args.output_dir))
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
