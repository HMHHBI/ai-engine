from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import pathlib
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.config import settings
from app.db.models import DocumentChunk
from app.db.session import session_scope
from app.repositories.vector_repo import VectorRepository
from app.services.embedding_service import EmbeddingService

DEFAULT_K_VALUES = (1, 3, 5, 10)
DEFAULT_DATASET = pathlib.Path("scripts/evaluations/rag_quality_dataset.json")
DEFAULT_RESULTS_DIR = pathlib.Path("evaluation-results")


@dataclass(frozen=True)
class EvaluationQuery:
    query_id: str
    user_id: int
    document_id: int
    query: str
    relevant_chunk_indexes: frozenset[int]
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
    k_metrics: Dict[str, Dict[str, float]]
    retrieved: List[RetrievedChunk]


def load_dataset(path: pathlib.Path) -> List[EvaluationQuery]:
    with path.open("r", encoding="utf-8") as h:
        payload = json.load(h)
    return [
        EvaluationQuery(
            query_id=item["query_id"],
            user_id=item["user_id"],
            document_id=item["document_id"],
            query=item["query"].strip(),
            relevant_chunk_indexes=frozenset(item.get("relevant_chunk_indexes", [])),
            relevant_chunk_ids=frozenset(item.get("relevant_chunk_ids", [])),
            reference_answer=item.get("reference_answer"),
        )
        for item in payload.get("queries", [])
    ]


def is_relevant(r: RetrievedChunk, eq: EvaluationQuery) -> bool:
    if r.chunk_id in eq.relevant_chunk_ids:
        return True
    if r.chunk_index is not None and r.chunk_index in eq.relevant_chunk_indexes:
        return True
    return False


def hit_rate_at_k(retrieved: List[RetrievedChunk], eq: EvaluationQuery, k: int) -> float:
    return float(any(is_relevant(r, eq) for r in retrieved[:k]))


def reciprocal_rank_at_k(retrieved: List[RetrievedChunk], eq: EvaluationQuery, k: int) -> float:
    for rank, r in enumerate(retrieved[:k], start=1):
        if is_relevant(r, eq):
            return 1.0 / rank
    return 0.0


def context_precision_at_k(retrieved: List[RetrievedChunk], eq: EvaluationQuery, k: int) -> float:
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    return sum(1 for r in top_k if is_relevant(r, eq)) / len(top_k)


def context_recall_at_k(retrieved: List[RetrievedChunk], eq: EvaluationQuery, k: int) -> float:
    total = len(eq.relevant_chunk_indexes | eq.relevant_chunk_ids)
    if total == 0:
        return 0.0
    matched = len(
        {r.chunk_id for r in retrieved[:k] if r.chunk_id in eq.relevant_chunk_ids}
        | {r.chunk_index for r in retrieved[:k] if r.chunk_index in eq.relevant_chunk_indexes}
    )
    return min(matched / total, 1.0)


def calculate_query_metrics(
    retrieved: List[RetrievedChunk], eq: EvaluationQuery, k_values: tuple[int, ...]
) -> Dict[str, Dict[str, float]]:
    return {
        str(k): {
            "requested_k": float(k),
            "returned_count": float(len(retrieved[:k])),
            "hit_rate": hit_rate_at_k(retrieved, eq, k),
            "mrr": reciprocal_rank_at_k(retrieved, eq, k),
            "context_precision": context_precision_at_k(retrieved, eq, k),
            "context_recall": context_recall_at_k(retrieved, eq, k),
        }
        for k in k_values
    }


def aggregate_metrics(
    evaluations: List[QueryEvaluation], k_values: tuple[int, ...]
) -> Dict[str, Dict[str, float]]:
    aggregate: Dict[str, Dict[str, float]] = {}
    metric_keys = ("hit_rate", "mrr", "context_precision", "context_recall")
    for k in k_values:
        k_str = str(k)
        accumulators = {name: [] for name in metric_keys}
        for ev in evaluations:
            m = ev.k_metrics[k_str]
            for name in metric_keys:
                accumulators[name].append(m[name])
        aggregate[k_str] = {
            name: round(statistics.mean(scores), 4)
            for name, scores in accumulators.items()
        }
    return aggregate


def build_failures(aggregate: Dict[str, Dict[str, float]]) -> List[str]:
    thresholds = {
        "1": {"hit_rate": 0.70},
        "3": {"hit_rate": 0.85},
        "5": {"hit_rate": 0.90, "mrr": 0.80},
        "10": {"hit_rate": 0.95},
    }
    failures = []
    for k, metrics in thresholds.items():
        for metric, threshold in metrics.items():
            val = aggregate.get(k, {}).get(metric, 0.0)
            if val < threshold:
                failures.append(f"K={k} {metric}: {val:.4f} < {threshold:.4f}")
    return failures


async def embed_query(query: str) -> List[float]:
    provider = settings.DEFAULT_EMBEDDING_PROVIDER.value
    embedding = await EmbeddingService.generate_embedding(
        text=query,
        model_provider=provider,
    )
    if not embedding:
        raise RuntimeError(f"Embedding failed for provider '{provider}'.")
    return embedding


def retrieve(eq: EvaluationQuery, query_vector: List[float], max_k: int) -> List[RetrievedChunk]:
    results = VectorRepository.search_similar_chunks(
        user_id=eq.user_id,
        document_id=eq.document_id,
        query_vector=query_vector,
        top_k=max_k,
    )
    return [
        RetrievedChunk(
            chunk_id=r["id"],
            document_id=r["document_id"],
            chunk_index=r.get("chunk_index"),
            content=r["content"],
            distance=float(r["distance"]),
        )
        for r in results
    ]


def write_reports(
    dataset_path: pathlib.Path,
    evaluations: List[QueryEvaluation],
    aggregate: Dict[str, Dict[str, float]],
    failures: List[str],
    output_dir: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"rag-quality-{timestamp}.json"
    json_payload = {
        "evaluation": {
            "timestamp_utc": timestamp,
            "dataset": str(dataset_path),
            "query_count": len(evaluations),
            "k_values": list(DEFAULT_K_VALUES),
            "passed": not failures,
        },
        "aggregate_metrics": aggregate,
        "failures": failures,
    }
    with json_path.open("w", encoding="utf-8") as h:
        json.dump(json_payload, h, indent=2)

    md_path = output_dir / f"rag-quality-{timestamp}.md"
    status_str = "PASSED" if not failures else "FAILED"
    lines = [
        "# RAG Retrieval Quality Evaluation Report",
        "",
        f"- **Timestamp (UTC):** `{timestamp}`",
        f"- **Status:** `{status_str}`",
        f"- **Queries Evaluated:** `{len(evaluations)}`",
        "",
        "## Summary Metrics",
        "",
        "| K | Hit Rate | MRR | Precision | Recall |",
        "|---|---|---|---|---|",
    ]
    for k in DEFAULT_K_VALUES:
        m = aggregate[str(k)]
        lines.append(
            f"| {k} | {m['hit_rate']:.4f} | {m['mrr']:.4f} | {m['context_precision']:.4f} | {m['context_recall']:.4f} |"
        )

    with md_path.open("w", encoding="utf-8") as h:
        h.write("\n".join(lines) + "\n")

    return json_path, md_path


async def run(dataset_path: pathlib.Path, output_dir: pathlib.Path) -> int:
    queries = load_dataset(dataset_path)
    evaluations: List[QueryEvaluation] = []

    for idx, eq in enumerate(queries, start=1):
        print(f"[{idx}/{len(queries)}] Evaluating {eq.query_id}...")
        q_vec = await embed_query(eq.query)
        retrieved = retrieve(eq, q_vec, max(DEFAULT_K_VALUES))
        m = calculate_query_metrics(retrieved, eq, DEFAULT_K_VALUES)
        evaluations.append(
            QueryEvaluation(
                query_id=eq.query_id,
                user_id=eq.user_id,
                document_id=eq.document_id,
                k_metrics=m,
                retrieved=retrieved,
            )
        )

    aggregate = aggregate_metrics(evaluations, DEFAULT_K_VALUES)
    failures = build_failures(aggregate)
    json_path, md_path = write_reports(dataset_path, evaluations, aggregate, failures, output_dir)

    print("\n==================================================")
    print("  P3-02 RAG RETRIEVAL QUALITY EVALUATION")
    print("==================================================")
    print(f"{'K':<6}{'Hit Rate':<14}{'MRR':<14}{'Precision':<14}{'Recall':<14}")
    print("-" * 62)
    for k in DEFAULT_K_VALUES:
        metrics = aggregate[str(k)]
        print(
            f"{k:<6}"
            f"{metrics['hit_rate']:<14.4f}"
            f"{metrics['mrr']:<14.4f}"
            f"{metrics['context_precision']:<14.4f}"
            f"{metrics['context_recall']:<14.4f}"
        )
    print("\nSTATUS: " + ("PASSED" if not failures else "FAILED"))
    print(f"\nArtifacts generated:")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")
    return 0 if not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=pathlib.Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args()
    code = asyncio.run(run(args.dataset, args.output_dir))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
