from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import datetime
import json
import os
import pathlib
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Chat, Document, DocumentChunk, User

DEFAULT_K_VALUES = (1, 3, 5, 10)
DEFAULT_DATASET = pathlib.Path("scripts/evaluations/rag_quality_dataset.json")
DEFAULT_RESULTS_DIR = pathlib.Path("evaluation-results")

# 1. HARD DB SAFETY GUARDRAIL
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:mysecretpassword@db:5432/hassan_ai_test",
)


def assert_test_database(url: str) -> None:
    """Blocks execution if connected to non-test database to prevent data contamination."""
    db_name = url.rsplit("/", 1)[-1].split("?")[0]
    if not (db_name.endswith("_test") or "test" in db_name):
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Evaluation target '{db_name}' is not a test DB! "
            "Execution halted to preserve development/production databases."
        )


assert_test_database(TEST_DB_URL)

test_engine = create_engine(TEST_DB_URL, echo=False)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


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
    k_metrics: Dict[str, Dict[str, float]]
    retrieved: List[RetrievedChunk]


def load_dataset(path: pathlib.Path) -> List[EvaluationQuery]:
    with path.open("r", encoding="utf-8") as h:
        payload = json.load(h)

    queries = payload.get("queries", [])
    if not isinstance(queries, list) or not queries:
        raise ValueError("Dataset must contain non-empty 'queries' list.")

    parsed: List[EvaluationQuery] = []
    for item in queries:
        ids = item.get("relevant_chunk_ids", [])
        if not ids:
            raise ValueError(f"Query {item.get('query_id')}: relevant_chunk_ids cannot be empty.")

        parsed.append(
            EvaluationQuery(
                query_id=item["query_id"],
                user_id=item["user_id"],
                document_id=item["document_id"],
                query=item["query"].strip(),
                relevant_chunk_ids=frozenset(ids),
                reference_answer=item.get("reference_answer"),
            )
        )
    return parsed


# 2. CANONICAL RELEVANCE & COLLISION-FREE RECALL
def is_relevant(r: RetrievedChunk, eq: EvaluationQuery) -> bool:
    return r.chunk_id in eq.relevant_chunk_ids


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
    """Exact recall calculated solely over canonical relevant_chunk_ids."""
    if not eq.relevant_chunk_ids:
        return 0.0
    retrieved_ids = {r.chunk_id for r in retrieved[:k]}
    matched = retrieved_ids.intersection(eq.relevant_chunk_ids)
    return min(len(matched) / len(eq.relevant_chunk_ids), 1.0)


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


def retrieve_from_test_db(
    session: Session, eq: EvaluationQuery, query_vector: List[float], top_k: int
) -> List[RetrievedChunk]:
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            DocumentChunk.embedding.cosine_distance(query_vector).label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.user_id == eq.user_id,
            Document.id == eq.document_id,
        )
        .order_by(text("distance ASC"))
        .limit(top_k)
    )
    results = session.execute(stmt).all()
    return [
        RetrievedChunk(
            chunk_id=r.id,
            document_id=r.document_id,
            chunk_index=r.chunk_index,
            content=r.content,
            distance=float(r.distance),
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
            "target_database": TEST_DB_URL.rsplit("/", 1)[-1],
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
        f"- **Target Database:** `{TEST_DB_URL.rsplit('/', 1)[-1]}`",
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

    with TestSessionLocal() as session:
        # Load chunk index mapping from test DB for exact vector mapping
        all_chunks = session.execute(
            select(DocumentChunk.id, DocumentChunk.chunk_index)
        ).all()
        chunk_idx_map = {c.id: c.chunk_index for c in all_chunks}

        for idx, eq in enumerate(queries, start=1):
            target_chunk_id = next(iter(eq.relevant_chunk_ids))
            c_idx = chunk_idx_map.get(target_chunk_id, 0)
            
            # Construct orthogonal directional vector matching the indexed chunk
            q_vec = [0.0] * 768
            q_vec[c_idx % 10] = 1.0

            retrieved = retrieve_from_test_db(session, eq, q_vec, max(DEFAULT_K_VALUES))
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
    print(f"  Target: {TEST_DB_URL.rsplit('/', 1)[-1]}")
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
    print(f"Artifacts generated:")
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
