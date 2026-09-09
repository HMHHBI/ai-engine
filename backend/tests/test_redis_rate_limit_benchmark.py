"""Tests for P2-06 Redis and rate-limit benchmarking harness."""

from scripts.benchmarks.redis_rate_limit_benchmark import (
    compute_latencies,
    benchmark_layer4_failure_semantics,
)


def test_compute_latencies_summary():
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    res = compute_latencies(data)
    assert res["min"] == 10.0
    assert res["max"] == 50.0
    assert res["p50"] == 30.0
    assert res["avg"] == 30.0


def test_compute_latencies_empty():
    res = compute_latencies([])
    assert res["p50"] == 0.0
    assert res["avg"] == 0.0


def test_layer4_failure_semantics():
    res = benchmark_layer4_failure_semantics()
    assert res["unreachable_redis_raises"] is True
    assert "fail-closed" in res["behavior"]
