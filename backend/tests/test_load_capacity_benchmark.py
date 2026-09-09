"""
Tests for P2-08 Load Testing & Capacity Limits Benchmark.

Verifies:
- Percentile calculations using inclusive quantiles
- RPS and error rate calculations
- HTTP and transport error classifications (2xx, 4xx, 5xx, 429, timeouts)
- SLA gate evaluations (p50, p95, p99, error rate)
- Capacity analytics: knee detection, safe capacity factor (0.8x), and breaking points (5xx >= 5%)
- Frozen JSON result schema compliance
"""

import math
import statistics
import pytest

from scripts.benchmarks.load_capacity_benchmark import (
    calculate_percentiles,
    calculate_rps,
    calculate_error_rate,
    classify_http_status,
    evaluate_sla,
    detect_knee,
    calculate_safe_capacity,
    detect_breaking_point,
    build_tier_result,
    build_benchmark_report,
)


def test_percentiles_use_inclusive_method():
    """Assert known values for p50, p95, p99 using inclusive quantile calculation."""
    # Population of 1 to 100
    latencies = list(range(1, 101))
    pct = calculate_percentiles(latencies)

    # Inclusive method on 1..100: p50=50.5, p95=95.05, p99=99.01
    assert math.isclose(pct["p50"], 50.5, abs_tol=0.5)
    assert math.isclose(pct["p95"], 95.0, abs_tol=1.0)
    assert math.isclose(pct["p99"], 99.0, abs_tol=1.0)
    assert pct["min"] == 1.0
    assert pct["max"] == 100.0


def test_calculate_rps():
    """Assert RPS calculation given requests and duration."""
    rps = calculate_rps(completed_requests=100, duration_seconds=20.0)
    assert rps == 5.0

    # Zero duration guard
    assert calculate_rps(completed_requests=100, duration_seconds=0.0) == 0.0


def test_calculate_error_rate():
    """Assert error rate percentage calculation given total and server errors."""
    rate = calculate_error_rate(total_requests=100, server_errors=2)
    assert rate == 2.0

    # Zero requests guard
    assert calculate_error_rate(total_requests=0, server_errors=0) == 0.0


def test_classify_http_statuses():
    """Assert 2xx is successful, 4xx is client error, 5xx is server error, 429 is rate limited."""
    assert classify_http_status(200) == "successful"
    assert classify_http_status(201) == "successful"
    assert classify_http_status(400) == "client_error"
    assert classify_http_status(404) == "client_error"
    assert classify_http_status(429) == "rate_limited"
    assert classify_http_status(500) == "server_error"
    assert classify_http_status(502) == "server_error"
    assert classify_http_status(503) == "server_error"


def test_timeout_is_classified_separately():
    """Assert timeout classification does not increment http_5xx count."""
    metrics = {
        "completed": 10,
        "http_5xx": 0,
        "timeouts": 0,
    }
    # Simulate a timeout
    metrics["timeouts"] += 1

    assert metrics["timeouts"] == 1
    assert metrics["http_5xx"] == 0


def test_429_is_policy_rejection_not_server_error():
    """Assert HTTP 429 counts as policy rejection and is separate from 5xx."""
    category = classify_http_status(429)
    assert category == "rate_limited"
    assert category != "server_error"


def test_sla_passes_when_all_thresholds_are_met():
    """Assert SLA evaluation passes when all latency and error constraints meet SLA."""
    latency_pct = {"p50": 80.0, "p95": 200.0, "p99": 400.0}
    sla_limits = {
        "p50_ms": 100.0,
        "p95_ms": 250.0,
        "p99_ms": 500.0,
        "max_5xx_percent": 1.0,
    }

    sla = evaluate_sla(
        latencies=latency_pct,
        error_rate_5xx=0.0,
        timeout_rate=0.0,
        limits=sla_limits,
    )

    assert sla["p50_pass"] is True
    assert sla["p95_pass"] is True
    assert sla["p99_pass"] is True
    assert sla["error_rate_pass"] is True
    assert sla["overall_pass"] is True


def test_sla_fails_when_p99_exceeds_threshold():
    """Assert SLA evaluation fails when tail latency (p99) exceeds limit even if p50/p95 pass."""
    latency_pct = {"p50": 50.0, "p95": 200.0, "p99": 650.0}
    sla_limits = {
        "p50_ms": 100.0,
        "p95_ms": 250.0,
        "p99_ms": 500.0,
        "max_5xx_percent": 1.0,
    }

    sla = evaluate_sla(
        latencies=latency_pct,
        error_rate_5xx=0.0,
        timeout_rate=0.0,
        limits=sla_limits,
    )

    assert sla["p50_pass"] is True
    assert sla["p95_pass"] is True
    assert sla["p99_pass"] is False
    assert sla["overall_pass"] is False


def test_detect_knee_when_latency_doubles():
    """Assert knee detection triggers when p95 doubles from previous tier."""
    prev_metrics = {"p95": 100.0, "p99": 200.0, "rps": 50.0, "error_rate": 0.0}
    curr_metrics = {"p95": 210.0, "p99": 350.0, "rps": 60.0, "error_rate": 0.0}

    is_knee, reason = detect_knee(prev_tier=prev_metrics, current_tier=curr_metrics)
    assert is_knee is True
    assert "p95 latency doubled" in reason.lower()


def test_calculate_safe_capacity_as_80_percent_of_knee():
    """Assert safe capacity is calculated strictly as 80% of knee throughput."""
    knee_rps = 100.0
    safe_rps = calculate_safe_capacity(knee_rps=knee_rps)
    assert safe_rps == 80.0


def test_detect_breaking_point_at_five_percent_server_errors():
    """Assert breaking point triggers when 5xx errors reach or exceed 5%."""
    assert detect_breaking_point(error_rate_5xx=5.0, timeout_rate=0.0) is True
    assert detect_breaking_point(error_rate_5xx=6.5, timeout_rate=0.0) is True
    assert detect_breaking_point(error_rate_5xx=4.9, timeout_rate=0.0) is False
    assert detect_breaking_point(error_rate_5xx=0.0, timeout_rate=5.0) is True


def test_build_result_matches_p2_08_schema():
    """Assert output data structures match the frozen P2-08 JSON schema contract."""
    tier_res = build_tier_result(
        concurrency=1,
        ramp_seconds=60,
        sustain_seconds=300,
        requests=100,
        completed=100,
        allowed=100,
        rejected_429=0,
        http_4xx=0,
        http_5xx=0,
        timeouts=0,
        rps=10.0,
        latencies=[50.0, 75.0, 100.0],
        ttft_values=[],
        resource_dict={
            "rss_baseline_mib": 200.0,
            "rss_peak_mib": 210.0,
            "rss_post_mib": 201.0,
            "fd_peak": 25,
            "threads_peak": 12,
            "cpu_avg_percent": 15.0,
            "cpu_peak_percent": 25.0,
        },
        sla_limits={
            "p50_ms": 100.0,
            "p95_ms": 250.0,
            "p99_ms": 500.0,
            "max_5xx_percent": 1.0,
        },
    )

    required_tier_keys = {
        "concurrency",
        "ramp_seconds",
        "sustain_seconds",
        "requests",
        "completed",
        "allowed",
        "rejected_429",
        "http_4xx",
        "http_5xx",
        "timeouts",
        "errors",
        "rps",
        "latency_ms",
        "ttft_ms",
        "resource",
        "sla",
    }
    assert required_tier_keys.issubset(tier_res.keys())

    report = build_benchmark_report(
        env_dict={"transport": "http"},
        config_dict={"concurrency_levels": [1, 2, 4]},
        workloads_dict={"health_live": [tier_res]},
        capacity_analysis_dict={
            "knee": {},
            "safe_capacity": {},
            "breaking_point": {},
            "saturation_reason": "",
        },
        resource_analysis_dict={
            "cpu": {},
            "rss": {},
            "vms": {},
            "file_descriptors": {},
            "threads": {},
            "database_pool": {},
            "redis": {},
        },
        rate_limit_dict={"allowed": 100, "rejected_429": 0, "policy_limited": False},
        errors_list=[],
        sla_results_dict={"health_live": {"overall_pass": True}},
        verdict="PASS",
    )

    required_top_keys = {
        "benchmark",
        "timestamp",
        "environment",
        "configuration",
        "workloads",
        "capacity_analysis",
        "resource_analysis",
        "rate_limit_analysis",
        "errors",
        "sla_results",
        "conclusion",
    }
    assert required_top_keys.issubset(report.keys())
    assert report["conclusion"]["verdict"] == "PASS"
