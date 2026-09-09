"""Tests for P2-07 memory & resource profiling benchmark."""

import os
import pytest
from scripts.benchmarks.memory_resource_benchmark import (
    MemorySnapshot,
    ProcessResourceSampler,
    bytes_to_mib,
    calculate_retention,
    detect_growth,
    discover_backend_pid,
)


def test_snapshot_structure():
    sampler = ProcessResourceSampler(os.getpid())
    snap = sampler.capture_snapshot()
    assert isinstance(snap, MemorySnapshot)
    assert snap.rss_bytes > 0
    assert snap.vms_bytes > 0
    assert snap.thread_count >= 1
    assert isinstance(snap.gc_gen0, int)
    assert snap.fd_count is None or isinstance(snap.fd_count, int)


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
    # 100 MiB baseline: 5% is 5 MiB, so 10 MiB floor applies
    res_100 = calculate_retention(100.0, 108.0)
    assert res_100["allowed_delta_mib"] == 10.0
    assert res_100["acceptable"] is True

    # 500 MiB baseline: 5% is 25 MiB, so 25 MiB applies
    res_500 = calculate_retention(500.0, 520.0)
    assert res_500["allowed_delta_mib"] == 25.0
    assert res_500["acceptable"] is True


def test_peak_is_not_leak():
    res = calculate_retention(100.0, 102.0)
    assert res["acceptable"] is True


def test_persistent_growth_detection():
    # Strictly increasing sequence across cycles indicates monotonic growth
    assert detect_growth([100.0, 105.0, 111.0, 118.0, 126.0]) is True


def test_recovered_repeated_cycles():
    # Fluctuations that recover are not monotonic growth
    assert detect_growth([100.0, 120.0, 102.0, 125.0, 103.0]) is False


def test_unsupported_fd_platform(monkeypatch):
    sampler = ProcessResourceSampler(os.getpid())
    monkeypatch.setattr(sampler.process, "num_fds", lambda: (_ for _ in ()).throw(AttributeError("unsupported")))
    snap = sampler.capture_snapshot()
    assert snap.fd_count is None


def test_pid_discovery():
    pid = discover_backend_pid()
    assert isinstance(pid, int)
    assert pid > 0


@pytest.mark.asyncio
async def test_integration_smoke_sampler():
    sampler = ProcessResourceSampler(os.getpid())
    snap1 = sampler.capture_snapshot()
    snap2 = sampler.capture_snapshot()
    ret = calculate_retention(bytes_to_mib(snap1.rss_bytes), bytes_to_mib(snap2.rss_bytes))
    assert "acceptable" in ret
    assert isinstance(ret["recovery_delta_mib"], float)
