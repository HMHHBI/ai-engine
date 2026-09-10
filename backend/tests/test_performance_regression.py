"""
P2-09: Performance Regression Contracts.

Normal CI contract:
- deterministic
- synthetic measurements only
- no HTTP
- no database
- no Redis
- no Ollama
- no Gemini
- no OpenAI

Real capacity characterization remains owned by P2-08.
"""

from __future__ import annotations

from statistics import quantiles
from typing import Dict, List

import pytest

WORKLOAD_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "health_live": {
        "p50_ms": 100.0,
        "p95_ms": 250.0,
        "p99_ms": 500.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
    "health_ready": {
        "p50_ms": 150.0,
        "p95_ms": 500.0,
        "p99_ms": 1000.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
    "chat_history": {
        "p50_ms": 250.0,
        "p95_ms": 750.0,
        "p99_ms": 1500.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
    "pdf_ingestion": {
        "p50_ms": 5000.0,
        "p95_ms": 10000.0,
        "p99_ms": 15000.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
    "streaming_non_rag": {
        "p50_ms": 3000.0,
        "p95_ms": 7000.0,
        "p99_ms": 10000.0,
        "ttft_p50_ms": 1000.0,
        "ttft_p95_ms": 3000.0,
        "ttft_p99_ms": 5000.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
    "streaming_rag": {
        "p50_ms": 3000.0,
        "p95_ms": 7000.0,
        "p99_ms": 10000.0,
        "ttft_p50_ms": 1000.0,
        "ttft_p95_ms": 3000.0,
        "ttft_p99_ms": 5000.0,
        "max_5xx_percent": 1.0,
        "max_timeout_percent": 1.0,
    },
}


THROUGHPUT_THRESHOLDS = {
    # P2-03: ~20.12 emb/s at C1; ~20-22 emb/s saturation.
    # 80% of the lower observed saturation point.
    "embedding_vectors_per_second": 16.0,
    # P2-04: 247.66 QPS at C8.
    "rag_retrieval_qps": 198.13,
    # P2-06: ~2438 QPS at C50.
    "redis_qps": 1950.0,
}


# P2-07:
# post-GC recovery delta = 0.637 MiB
# authoritative retention threshold = 11.775 MiB
MAX_POST_GC_MEMORY_DELTA_MIB = 11.775


def percentile(values: List[float], percentile_value: int) -> float:
    ordered = sorted(values)

    if not ordered:
        return 0.0

    if len(ordered) == 1:
        return ordered[0]

    return quantiles(
        ordered,
        n=100,
        method="inclusive",
    )[percentile_value - 1]


def summarize(values: List[float]) -> Dict[str, float]:
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def standard_sla(
    workload: str,
    latency: List[float],
    error_rate_5xx: float = 0.0,
    timeout_rate: float = 0.0,
) -> Dict[str, bool]:
    limits = WORKLOAD_THRESHOLDS[workload]
    pct = summarize(latency)

    p50 = pct["p50"] <= limits["p50_ms"]
    p95 = pct["p95"] <= limits["p95_ms"]
    p99 = pct["p99"] <= limits["p99_ms"]

    errors = (
        error_rate_5xx < limits["max_5xx_percent"]
        and timeout_rate < limits["max_timeout_percent"]
    )

    return {
        "p50_pass": p50,
        "p95_pass": p95,
        "p99_pass": p99,
        "error_rate_pass": errors,
        "overall_pass": p50 and p95 and p99 and errors,
    }


def streaming_sla(
    workload: str,
    duration: List[float],
    ttft: List[float],
    error_rate_5xx: float = 0.0,
    timeout_rate: float = 0.0,
) -> Dict[str, bool]:
    limits = WORKLOAD_THRESHOLDS[workload]

    duration_pct = summarize(duration)
    ttft_pct = summarize(ttft)

    duration_pass = (
        duration_pct["p50"] <= limits["p50_ms"]
        and duration_pct["p95"] <= limits["p95_ms"]
        and duration_pct["p99"] <= limits["p99_ms"]
    )

    ttft_pass = (
        ttft_pct["p50"] <= limits["ttft_p50_ms"]
        and ttft_pct["p95"] <= limits["ttft_p95_ms"]
        and ttft_pct["p99"] <= limits["ttft_p99_ms"]
    )

    error_pass = (
        error_rate_5xx < limits["max_5xx_percent"]
        and timeout_rate < limits["max_timeout_percent"]
    )

    return {
        "duration_pass": duration_pass,
        "ttft_pass": ttft_pass,
        "error_rate_pass": error_pass,
        "overall_pass": (duration_pass and ttft_pass and error_pass),
    }


def evaluate_throughput(metric: str, measured_throughput: float) -> bool:
    floor = THROUGHPUT_THRESHOLDS[metric]
    return measured_throughput >= floor


def evaluate_memory_delta(observed_delta_mib: float) -> bool:
    return observed_delta_mib <= MAX_POST_GC_MEMORY_DELTA_MIB


def test_latency_contract_matrix_is_frozen():
    assert WORKLOAD_THRESHOLDS == {
        "health_live": {
            "p50_ms": 100.0,
            "p95_ms": 250.0,
            "p99_ms": 500.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
        "health_ready": {
            "p50_ms": 150.0,
            "p95_ms": 500.0,
            "p99_ms": 1000.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
        "chat_history": {
            "p50_ms": 250.0,
            "p95_ms": 750.0,
            "p99_ms": 1500.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
        "pdf_ingestion": {
            "p50_ms": 5000.0,
            "p95_ms": 10000.0,
            "p99_ms": 15000.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
        "streaming_non_rag": {
            "p50_ms": 3000.0,
            "p95_ms": 7000.0,
            "p99_ms": 10000.0,
            "ttft_p50_ms": 1000.0,
            "ttft_p95_ms": 3000.0,
            "ttft_p99_ms": 5000.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
        "streaming_rag": {
            "p50_ms": 3000.0,
            "p95_ms": 7000.0,
            "p99_ms": 10000.0,
            "ttft_p50_ms": 1000.0,
            "ttft_p95_ms": 3000.0,
            "ttft_p99_ms": 5000.0,
            "max_5xx_percent": 1.0,
            "max_timeout_percent": 1.0,
        },
    }


@pytest.mark.parametrize(
    "workload",
    [
        "health_live",
        "health_ready",
        "chat_history",
        "pdf_ingestion",
    ],
)
def test_standard_workload_passes_with_healthy_synthetic_measurements(
    workload: str,
):
    limits = WORKLOAD_THRESHOLDS[workload]

    values = [limits["p50_ms"] * 0.50] * 100

    result = standard_sla(workload, values)

    assert result["overall_pass"] is True


def test_health_live_p95_regression_fails():
    values = [50.0] * 94 + [251.0] * 6

    result = standard_sla("health_live", values)

    assert result["p95_pass"] is False
    assert result["overall_pass"] is False


def test_health_live_p99_regression_fails():
    values = [50.0] * 98 + [501.0] * 2

    result = standard_sla("health_live", values)

    assert result["p99_pass"] is False
    assert result["overall_pass"] is False


def test_error_rate_contract_is_strictly_below_one_percent():
    passing = standard_sla(
        "health_live",
        [50.0] * 100,
        error_rate_5xx=0.99,
    )

    failing = standard_sla(
        "health_live",
        [50.0] * 100,
        error_rate_5xx=1.0,
    )

    assert passing["error_rate_pass"] is True
    assert failing["error_rate_pass"] is False


def test_timeout_contract_is_strictly_below_one_percent():
    passing = standard_sla(
        "health_live",
        [50.0] * 100,
        timeout_rate=0.99,
    )

    failing = standard_sla(
        "health_live",
        [50.0] * 100,
        timeout_rate=1.0,
    )

    assert passing["error_rate_pass"] is True
    assert failing["error_rate_pass"] is False


@pytest.mark.parametrize(
    "workload",
    [
        "streaming_non_rag",
        "streaming_rag",
    ],
)
def test_streaming_contract_passes_when_duration_and_ttft_pass(
    workload: str,
):
    result = streaming_sla(
        workload,
        duration=[2000.0] * 100,
        ttft=[500.0] * 100,
    )

    assert result["duration_pass"] is True
    assert result["ttft_pass"] is True
    assert result["overall_pass"] is True


def test_streaming_contract_fails_when_ttft_regresses():
    result = streaming_sla(
        "streaming_non_rag",
        duration=[2000.0] * 100,
        ttft=[500.0] * 98 + [5001.0] * 2,
    )

    assert result["duration_pass"] is True
    assert result["ttft_pass"] is False
    assert result["overall_pass"] is False


def test_streaming_contract_fails_when_duration_regresses():
    result = streaming_sla(
        "streaming_rag",
        duration=[2000.0] * 98 + [10001.0] * 2,
        ttft=[500.0] * 100,
    )

    assert result["duration_pass"] is False
    assert result["ttft_pass"] is True
    assert result["overall_pass"] is False


def test_embedding_throughput_regression_evaluation():
    # Healthy (at/above floor)
    assert evaluate_throughput("embedding_vectors_per_second", 20.12) is True
    assert evaluate_throughput("embedding_vectors_per_second", 16.0) is True

    # Regressed (below floor)
    assert evaluate_throughput("embedding_vectors_per_second", 15.99) is False
    assert evaluate_throughput("embedding_vectors_per_second", 8.0) is False


def test_rag_retrieval_throughput_regression_evaluation():
    # Healthy (at/above floor)
    assert evaluate_throughput("rag_retrieval_qps", 247.66) is True
    assert evaluate_throughput("rag_retrieval_qps", 198.13) is True

    # Regressed (below floor)
    assert evaluate_throughput("rag_retrieval_qps", 198.12) is False
    assert evaluate_throughput("rag_retrieval_qps", 100.0) is False


def test_redis_throughput_regression_evaluation():
    # Healthy (at/above floor)
    assert evaluate_throughput("redis_qps", 2438.0) is True
    assert evaluate_throughput("redis_qps", 1950.0) is True

    # Regressed (below floor)
    assert evaluate_throughput("redis_qps", 1949.9) is False
    assert evaluate_throughput("redis_qps", 500.0) is False


def test_memory_delta_regression_evaluation():
    # Healthy (at/below retention threshold)
    assert evaluate_memory_delta(0.637) is True
    assert evaluate_memory_delta(11.775) is True

    # Regressed (above retention threshold)
    assert evaluate_memory_delta(11.776) is False
    assert evaluate_memory_delta(25.0) is False


def test_p2_09_is_provider_independent():
    """
    No provider/network dependency is permitted in the PR regression gate.
    """
    result = streaming_sla(
        "streaming_non_rag",
        duration=[2000.0] * 100,
        ttft=[500.0] * 100,
    )

    assert result["overall_pass"] is True
