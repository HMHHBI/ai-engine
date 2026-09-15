#!/usr/bin/env python3
"""Run P3-06 comparative benchmark across retrieval strategies and capture latency."""

import asyncio
import json
import statistics
from pathlib import Path
from time import perf_counter

from app.core.config import settings
from scripts.evaluations.rag_quality_eval import execute_evaluation, DEFAULT_DATASET, DEFAULT_K_VALUES

STRATEGIES_TO_COMPARE = [
    ("hybrid", "deterministic"),
    ("hybrid_rerank", "deterministic"),
    ("hybrid_cross_encoder_rerank", "cross_encoder"),
]

async def main():
    results = {}
    output_dir = Path("evaluation-results/p3_06_benchmark")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("STARTING P3-06 COMPARATIVE BENCHMARK (120 QUERIES)")
    print("=" * 70)

    for strat, provider in STRATEGIES_TO_COMPARE:
        print(f"\n>>> Running Benchmark: Strategy={strat} | Provider={provider}")
        start_t = perf_counter()
        eval_result = await execute_evaluation(
            dataset_path=DEFAULT_DATASET,
            output_dir=output_dir,
            k_values=DEFAULT_K_VALUES,
            strategy=strat,
            reranker_provider=provider,
        )
        elapsed = perf_counter() - start_t

        queries = eval_result.get("queries", [])
        rerank_lats = [q.get("rerank_latency_ms", 0.0) for q in queries if "rerank_latency_ms" in q]
        cand_lats = [q.get("candidate_latency_ms", 0.0) for q in queries if "candidate_latency_ms" in q]
        tot_lats = [q.get("total_latency_ms", 0.0) for q in queries if "total_latency_ms" in q]

        results[strat] = {
            "aggregate": eval_result["aggregate"],
            "elapsed_seconds": elapsed,
            "cold_start_ms": rerank_lats[0] if rerank_lats else 0.0,
            "rerank_p50_ms": statistics.median(rerank_lats[1:]) if len(rerank_lats) > 1 else (rerank_lats[0] if rerank_lats else 0.0),
            "rerank_p95_ms": sorted(rerank_lats[1:])[int(len(rerank_lats[1:]) * 0.95)] if len(rerank_lats) > 1 else 0.0,
            "total_p50_ms": statistics.median(tot_lats) if tot_lats else 0.0,
            "total_p95_ms": sorted(tot_lats)[int(len(tot_lats) * 0.95)] if tot_lats else 0.0,
        }

    # Summary Output
    print("\n" + "=" * 78)
    print("P3-06 BENCHMARK COMPARISON MATRIX")
    print("=" * 78)
    print(f"{'Strategy':<30} {'Hit@5':<10} {'MRR@5':<10} {'Rerank p50':<14} {'Total p95':<12}")
    print("-" * 78)
    for strat, data in results.items():
        agg = data["aggregate"].get("5", {})
        hit5 = agg.get("hit_rate", 0.0)
        mrr5 = agg.get("mrr", 0.0)
        r_p50 = data["rerank_p50_ms"]
        t_p95 = data["total_p95_ms"]
        print(f"{strat:<30} {hit5:<10.4f} {mrr5:<10.4f} {r_p50:<14.2f}ms {t_p95:<12.2f}ms")

    benchmark_summary_path = output_dir / "benchmark_summary.json"
    benchmark_summary_path.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed summary saved to {benchmark_summary_path}")

if __name__ == "__main__":
    asyncio.run(main())
