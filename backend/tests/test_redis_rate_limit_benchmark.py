"""Tests for P2-06 Redis and rate-limit benchmarking harness."""

import pytest
from scripts.benchmarks.redis_rate_limit_benchmark import (
    compute_latencies,
    benchmark_layer4_failure_semantics,
)


def test_compute_latencies_summary():
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    res = compute_latencies(data)
    assert res["min"] == 10.0
    assert res["max"] == 50.0
    assert res["avg"] == 30.0
    assert abs(res["p50"] - 30.0) < 1.0


def test_compute_latencies_single_and_empty():
    res_empty = compute_latencies([])
    assert res_empty["p50"] == 0.0
    assert res_empty["avg"] == 0.0

    res_single = compute_latencies([42.5])
    assert res_single["p50"] == 42.5
    assert res_single["min"] == 42.5


@pytest.mark.asyncio
async def test_layer4_failure_semantics_http_500():
    res = await benchmark_layer4_failure_semantics()
    assert res["direct_storage_raised"] is True
    assert res["http_status_code"] == 500
    assert "fail-closed" in res["behavior"]
    assert isinstance(res["http_response_body"], dict)
    assert res["http_response_body"].get("success") is False
    assert res["http_response_body"].get("error_code") == "unhandled_exception"
    assert res["http_response_body"].get("error") == "Internal Server Error"
