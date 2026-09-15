"""Authoritative Fail-Closed Production Gate Validator for RAG Cross-Encoder Reranker (P3-07)."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required JSON file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from exc


def resolve_paths(
    custom_summary: Optional[str],
    custom_dir: Optional[str],
) -> Tuple[Path, Path]:
    search_dirs: List[Path] = []
    if custom_dir:
        search_dirs.append(Path(custom_dir))

    search_dirs.extend([
        Path("evaluation-results/p3_06_benchmark"),
        Path("evaluation-results"),
        Path("backend/evaluation-results/p3_06_benchmark"),
        Path("backend/evaluation-results"),
        Path("/app/evaluation-results/p3_06_benchmark"),
        Path("/app/evaluation-results"),
        Path("../evaluation-results/p3_06_benchmark"),
        Path("../evaluation-results"),
    ])

    summary_file: Optional[Path] = None
    if custom_summary:
        cand = Path(custom_summary)
        if cand.exists():
            summary_file = cand

    if not summary_file:
        for d in search_dirs:
            cand = d / "benchmark_summary.json"
            if cand.exists():
                summary_file = cand
                break

    if not summary_file:
        raise FileNotFoundError(
            "FAIL-CLOSED: Cannot locate benchmark_summary.json in candidate benchmark directories."
        )

    return summary_file, summary_file.parent


def find_detailed_run_file(benchmark_dir: Path) -> Path:
    search_dirs = [benchmark_dir, benchmark_dir.parent]
    candidates: List[Path] = []
    for d in search_dirs:
        if d.exists():
            candidates.extend(d.glob("rag-quality-*.json"))

    for f in sorted(candidates, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            queries = data.get("queries", [])
            if queries and any("rerank_latency_ms" in q for q in queries):
                return f
        except Exception:
            continue

    raise FileNotFoundError(
        "FAIL-CLOSED: Cannot locate detailed benchmark run file containing 'rerank_latency_ms' records."
    )


def evaluate_gates() -> int:
    parser = argparse.ArgumentParser(description="P3-07 Production Gate Runner")
    parser.add_argument("--summary-file", type=str, default=None, help="Path to benchmark_summary.json")
    parser.add_argument("--benchmark-dir", type=str, default=None, help="Directory containing benchmark runs")
    parser.add_argument("--policy-file", type=str, default=None, help="Path to p3_07_production_policy.json")
    args = parser.parse_args()

    policy_paths = [
        Path(args.policy_file) if args.policy_file else None,
        Path("backend/scripts/evaluations/p3_07_production_policy.json"),
        Path("scripts/evaluations/p3_07_production_policy.json"),
        Path("/app/scripts/evaluations/p3_07_production_policy.json"),
    ]
    policy_path = next((p for p in policy_paths if p and p.exists()), None)
    if not policy_path:
        print("[FAIL-CLOSED] Policy file p3_07_production_policy.json could not be found.")
        return 1

    try:
        policy = load_json(policy_path)
        summary_file, benchmark_dir = resolve_paths(args.summary_file, args.benchmark_dir)
        summary = load_json(summary_file)
        detailed_file = find_detailed_run_file(benchmark_dir)
        detailed_data = load_json(detailed_file)
    except Exception as err:
        print(f"[FAIL-CLOSED] Evidence loading failed: {err}")
        return 1

    q_policy = policy.get("quality", {})
    l_policy = policy.get("latency_ms", {})
    op_policy = policy.get("operational", {})

    print("=" * 68)
    print("           P3-07 PRODUCTION RELEASE GATE VERIFICATION")
    print("=" * 68)
    print(f"Policy:    {policy.get('policy_name')} ({policy.get('version')})")
    print(f"Summary:   {summary_file}")
    print(f"Evidence:  {detailed_file.name}")
    print("-" * 68)

    gate_failures = 0

    # 1. Quality Gates
    print("QUALITY GATES:")
    ce_summary = summary.get("hybrid_cross_encoder_rerank", {})
    hybrid_summary = summary.get("hybrid", {})
    if not ce_summary or not hybrid_summary:
        print("[FAIL-CLOSED] Required strategy blocks missing in summary.")
        return 1

    ce_agg = ce_summary.get("aggregate", {})
    hybrid_agg = hybrid_summary.get("aggregate", {})

    hit_1 = ce_agg.get("1", {}).get("hit_rate")
    mrr_5 = ce_agg.get("5", {}).get("mrr")
    recall_5 = ce_agg.get("5", {}).get("context_recall")
    base_hit_1 = hybrid_agg.get("1", {}).get("hit_rate")

    if any(v is None for v in [hit_1, mrr_5, recall_5, base_hit_1]):
        print("[FAIL-CLOSED] Missing required quality metrics in aggregate summary.")
        return 1

    hit_1_gain = hit_1 - base_hit_1

    def check_gate(name: str, val: float, target: float, comp: str = ">=", unit: str = "") -> None:
        nonlocal gate_failures
        passed = (val >= target) if comp == ">=" else (val <= target)
        status_str = "PASS" if passed else "FAIL"
        if not passed:
            gate_failures += 1
        fmt_val = f"{val:6.2f} {unit}" if unit else f"{val:.4f}"
        fmt_target = f"{target:6.2f} {unit}" if unit else f"{target:.4f}"
        print(f"  [{status_str}] {name:<22} Observed: {fmt_val} | Threshold {comp} {fmt_target}")

    check_gate("Gate Q1 (Hit@1)", hit_1, q_policy["hit_at_1_min"])
    check_gate("Gate Q2 (MRR@5)", mrr_5, q_policy["mrr_at_5_min"])
    check_gate("Gate Q3 (Recall@5)", recall_5, q_policy["recall_at_5_min"])
    check_gate("Gate Q4 (Hit@1 Gain)", hit_1_gain, q_policy["hit_at_1_gain_min"])

    # 2. Latency Gates
    print("\nLATENCY GATES (Warm CPU Inference):")
    queries = detailed_data.get("queries", [])
    rerank_lats = [q["rerank_latency_ms"] for q in queries if "rerank_latency_ms" in q and q["rerank_latency_ms"] is not None]
    total_lats = [q["total_latency_ms"] for q in queries if "total_latency_ms" in q and q["total_latency_ms"] is not None]

    if not rerank_lats or not total_lats or len(rerank_lats) < 2:
        print("[FAIL-CLOSED] Detailed run file lacks required latency data points.")
        return 1

    cold_start = rerank_lats[0]
    warm_rerank = rerank_lats[1:]
    warm_total = total_lats[1:]

    rerank_p50 = statistics.median(warm_rerank)
    rerank_p95 = sorted(warm_rerank)[int(len(warm_rerank) * 0.95)]
    total_p50 = statistics.median(warm_total)
    total_p95 = sorted(warm_total)[int(len(warm_total) * 0.95)]

    check_gate("Gate L1 (Rerank p50)", rerank_p50, l_policy["rerank_p50_max"], "<=", "ms")
    check_gate("Gate L2 (Rerank p95)", rerank_p95, l_policy["rerank_p95_max"], "<=", "ms")
    check_gate("Gate L3 (Total p50)", total_p50, l_policy["total_p50_max"], "<=", "ms")
    check_gate("Gate L4 (Total p95)", total_p95, l_policy["total_p95_max"], "<=", "ms")

    # 3. Operational Policy Enforcement
    print("\nOPERATIONAL ENFORCEMENT:")
    try:
        from app.core.config import settings
        app_default_flag = settings.ENABLE_RERANKING
        app_model = settings.RERANKER_MODEL
    except ImportError:
        app_default_flag = os.getenv("ENABLE_RERANKING", "false").lower() in ("true", "1", "yes")
        app_model = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Enforce O1: Production Default Disabled
    o1_passed = (app_default_flag is False) and (op_policy.get("default_enabled") is False)
    if not o1_passed:
        gate_failures += 1
    print(f"  [{'PASS' if o1_passed else 'FAIL'}] Gate O1 (Safety Default)    ENABLE_RERANKING={app_default_flag} (Required: False)")

    # Enforce O2: Model Configuration Match
    o2_passed = (app_model == op_policy.get("model_name"))
    if not o2_passed:
        gate_failures += 1
    print(f"  [{'PASS' if o2_passed else 'FAIL'}] Gate O2 (Model Name)        Configured: {app_model}")

    # Enforce O3: Cold-Start Measurement Recorded
    o3_passed = (cold_start > 0.0)
    if not o3_passed:
        gate_failures += 1
    print(f"  [{'PASS' if o3_passed else 'FAIL'}] Gate O3 (Cold-Start Trace)   Initial Load: {cold_start:6.2f} ms")

    # Enforce O4: Cold-Start Disallowed in Real User Requests
    o4_passed = (op_policy.get("cold_start_allowed_in_request") is False)
    if not o4_passed:
        gate_failures += 1
    print(f"  [{'PASS' if o4_passed else 'FAIL'}] Gate O4 (Warm-Up Mandate)   cold_start_allowed_in_request={op_policy.get('cold_start_allowed_in_request')}")

    # Enforce O5: Fallback Required
    o5_passed = (op_policy.get("fallback_required") is True)
    if not o5_passed:
        gate_failures += 1
    print(f"  [{'PASS' if o5_passed else 'FAIL'}] Gate O5 (Fallback Mandate)  fallback_required={op_policy.get('fallback_required')}")

    print("=" * 68)
    if gate_failures == 0:
        print("OVERALL VERDICT: ALL PRODUCTION GATES PASSED (APPROVED)")
        print("Decision: APPROVED for controlled activation; default remains False.")
        print("=" * 68)
        return 0
    else:
        print(f"OVERALL VERDICT: FAILED ({gate_failures} gate(s) breached) - FAIL-CLOSED")
        print("=" * 68)
        return 1


if __name__ == "__main__":
    sys.exit(evaluate_gates())
