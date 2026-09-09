"""Tests for P2-07 memory & resource profiling harness and contract guarantees."""

import asyncio
import os
import pytest
import httpx

from scripts.benchmarks.memory_resource_benchmark import (
    MemorySnapshot,
    ProcessResourceSampler,
    build_text_pdf_bytes,
    bytes_to_mib,
    calculate_retention,
    detect_growth,
    discover_backend_pid,
    run_idle_baseline,
    run_m2_ingestion,
    run_m4_m5_streaming,
    run_sustained_streaming_10m,
)


def test_snapshot_structure():
    sampler = ProcessResourceSampler(os.getpid(), is_in_process=True)
    snap = sampler.capture_snapshot()
    assert isinstance(snap, MemorySnapshot)
    assert snap.rss_bytes > 0
    assert snap.vms_bytes > 0
    assert snap.thread_count >= 1
    assert isinstance(snap.gc_gen0, int)


def test_mib_conversion():
    assert bytes_to_mib(1024 * 1024) == 1.0
    assert bytes_to_mib(10 * 1024 * 1024) == 10.0
    assert bytes_to_mib(0) == 0.0


def test_retention_calculation_acceptable():
    res = calculate_retention(100.0, 105.0)
    assert res["recovery_delta_mib"] == 5.0
    assert res["acceptable"] is True


def test_retention_calculation_exceeded():
    res = calculate_retention(100.0, 120.0)
    assert res["recovery_delta_mib"] == 20.0
    assert res["acceptable"] is False


def test_retention_threshold_5_percent_vs_10_mib():
    res_100 = calculate_retention(100.0, 108.0)
    assert res_100["allowed_delta_mib"] == 10.0
    assert res_100["acceptable"] is True

    res_500 = calculate_retention(500.0, 520.0)
    assert res_500["allowed_delta_mib"] == 25.0
    assert res_500["acceptable"] is True


def test_strict_5_cycle_monotonic_growth_true():
    assert detect_growth([100.0, 105.0, 111.0, 118.0, 126.0], min_growth_step_mib=0.5) is True


def test_strict_5_cycle_growth_requires_five_points():
    assert detect_growth([100.0, 105.0, 111.0, 118.0], min_growth_step_mib=0.5) is False


def test_strict_5_cycle_allocator_noise_filtered():
    assert detect_growth([100.0, 100.02, 100.03, 100.05, 100.08], min_growth_step_mib=0.5) is False


def test_recovered_repeated_cycles():
    assert detect_growth([100.0, 120.0, 102.0, 125.0, 103.0]) is False


def test_build_text_pdf_bytes():
    pdf = build_text_pdf_bytes(page_count=3)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"/Type /Catalog" in pdf
    assert b"Page 1:" in pdf
    assert pdf.endswith(b"%%EOF\n")


def test_pid_discovery_validity():
    try:
        pid = discover_backend_pid()
        assert isinstance(pid, int)
        assert pid > 1
    except RuntimeError:
        pass


def test_unsupported_fd_platform(monkeypatch):
    sampler = ProcessResourceSampler(os.getpid(), is_in_process=True)
    monkeypatch.setattr(sampler.process, "num_fds", lambda: (_ for _ in ()).throw(AttributeError("unsupported")))
    snap = sampler.capture_snapshot()
    assert snap.fd_count is None


@pytest.mark.asyncio
async def test_failure_accounting_on_http_error():
    """Validates that HTTP errors are not swallowed and are recorded in metrics."""
    async def mock_handler(request: httpx.Request):
        return httpx.Response(500, json={"detail": "Internal error"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await run_m2_ingestion(client, {}, chat_id=1, concurrency=1, runs=2, pages=2)
        assert res["errors"] == 2
        assert res["completed"] == 0
        assert 500 in res["status_codes"]


@pytest.mark.asyncio
async def test_failure_accounting_on_streaming_error():
    """Validates streaming exception/failure tracking."""
    async def mock_handler(request: httpx.Request):
        return httpx.Response(503, json={"detail": "Service unavailable"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await run_m4_m5_streaming(client, {}, chat_id=1, concurrency=2, count=2, is_rag=False)
        assert res["errors"] == 2
        assert res["completed"] == 0
        assert 503 in res["status_codes"]


@pytest.mark.asyncio
async def test_sustained_streaming_scheduler():
    """Validates sustained streaming scheduler loop and continuous sampling."""
    async def mock_handler(request: httpx.Request):
        return httpx.Response(200, text="event: chunk\ndata: {}\n\n")

    transport = httpx.MockTransport(mock_handler)
    sampler = ProcessResourceSampler(os.getpid(), is_in_process=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        samples, stats = await run_sustained_streaming_10m(client, {}, chat_id=1, sampler=sampler, duration_s=1)
        assert len(samples) >= 1
        assert stats["completed"] > 0
        assert stats["errors"] == 0


@pytest.mark.asyncio
async def test_idle_baseline_aggregation():
    """Validates baseline sampling aggregation over duration window."""
    sampler = ProcessResourceSampler(os.getpid(), is_in_process=True)
    metrics = await run_idle_baseline(sampler, duration_s=2)
    assert metrics["sample_count"] == 2
    assert metrics["median_rss_mib"] > 0
    assert metrics["peak_rss_mib"] >= metrics["median_rss_mib"]
