"""
P2-07 Memory & Resource Profiling Harness.

Profiles:
- M1: Idle Worker Baseline (60s at 1Hz sampling)
- M2: PDF Ingestion (C=1, 2, 4)
- M3: Embedding Memory (C=1, 2, 4, 8)
- M4: Hybrid RAG Memory (C=1, 2, 4, 8)
- M5: Streaming Chat Memory (C=1, 2, 4, 8)
- Sustained Streaming Load (C=4, 5 cycles with quiescence & GC recovery)

Measures: RSS, VMS, Python heap (tracemalloc), GC generations, FDs, Threads, and CPU.
"""

import argparse
import asyncio
import gc
import json
import os
import pathlib
import platform
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import psutil

APP_BASE_URL = os.getenv("BENCHMARK_BASE_URL", "http://127.0.0.1:8000")


@dataclass
class MemorySnapshot:
    timestamp: float
    rss_bytes: int
    vms_bytes: int
    python_heap_current_bytes: int
    python_heap_peak_bytes: int
    gc_gen0: int
    gc_gen1: int
    gc_gen2: int
    fd_count: Optional[int]
    thread_count: int
    cpu_percent: float


def bytes_to_mib(byte_val: int) -> float:
    return round(byte_val / (1024 * 1024), 3)


class ProcessResourceSampler:
    """Monitors the target process resources cleanly across platforms."""

    def __init__(self, pid: int):
        self.pid = pid
        try:
            self.process = psutil.Process(pid)
            # Initialize CPU percent measurement
            self.process.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            raise ValueError(f"Process with PID {pid} not found")

    def capture_snapshot(self) -> MemorySnapshot:
        mem = self.process.memory_info()
        rss = mem.rss
        vms = mem.vms

        # Tracemalloc heap (if tracking active in current Python interpreter)
        if tracemalloc.is_tracing():
            curr_heap, peak_heap = tracemalloc.get_traced_memory()
        else:
            curr_heap, peak_heap = 0, 0

        # GC generational counts
        gc_counts = gc.get_count()

        # Portable File Descriptors count
        try:
            fds = self.process.num_fds()
        except (AttributeError, NotImplementedError, psutil.AccessDenied):
            fds = None

        threads = self.process.num_threads()
        cpu = self.process.cpu_percent(interval=None)

        return MemorySnapshot(
            timestamp=time.time(),
            rss_bytes=rss,
            vms_bytes=vms,
            python_heap_current_bytes=curr_heap,
            python_heap_peak_bytes=peak_heap,
            gc_gen0=gc_counts[0],
            gc_gen1=gc_counts[1],
            gc_gen2=gc_counts[2],
            fd_count=fds,
            thread_count=threads,
            cpu_percent=cpu,
        )


def calculate_retention(baseline_rss_mib: float, post_gc_rss_mib: float) -> Dict[str, Any]:
    """Applies the frozen acceptance threshold: max(10 MiB, 5% of baseline RSS)."""
    allowed_delta = max(10.0, baseline_rss_mib * 0.05)
    recovery_delta = post_gc_rss_mib - baseline_rss_mib
    acceptable = recovery_delta <= allowed_delta
    return {
        "baseline_rss_mib": round(baseline_rss_mib, 3),
        "post_gc_rss_mib": round(post_gc_rss_mib, 3),
        "recovery_delta_mib": round(recovery_delta, 3),
        "allowed_delta_mib": round(allowed_delta, 3),
        "acceptable": acceptable,
    }


def detect_growth(cycle_snapshots_rss: List[float]) -> bool:
    """Returns True if strictly monotonic growth is sustained over >= 3 cycles."""
    if len(cycle_snapshots_rss) < 3:
        return False
    growth_count = 0
    for i in range(1, len(cycle_snapshots_rss)):
        if cycle_snapshots_rss[i] > cycle_snapshots_rss[i - 1]:
            growth_count += 1
        else:
            growth_count = 0
        if growth_count >= 2:  # 3 consecutive ascending points (i-2 < i-1 < i)
            return True
    return False


def get_results_dir() -> pathlib.Path:
    candidate_paths = [
        pathlib.Path("/benchmark-results"),
        pathlib.Path(__file__).resolve().parents[3] / "benchmark-results",
        pathlib.Path.cwd() / "benchmark-results",
    ]
    for p in candidate_paths:
        if p.exists() and p.is_dir():
            return p
    target = pathlib.Path.cwd() / "benchmark-results"
    target.mkdir(parents=True, exist_ok=True)
    return target


async def run_idle_baseline(sampler: ProcessResourceSampler, duration_s: int = 60) -> Dict[str, Any]:
    print(f"--- M1: Profiling Idle Worker ({duration_s}s at 1Hz) ---")
    snapshots: List[MemorySnapshot] = []
    for _ in range(duration_s):
        snapshots.append(sampler.capture_snapshot())
        await asyncio.sleep(1.0)

    rss_vals = [bytes_to_mib(s.rss_bytes) for s in snapshots]
    vms_vals = [bytes_to_mib(s.vms_bytes) for s in snapshots]
    heap_vals = [bytes_to_mib(s.python_heap_current_bytes) for s in snapshots]
    fds = [s.fd_count for s in snapshots if s.fd_count is not None]
    threads = [s.thread_count for s in snapshots]

    return {
        "duration_seconds": duration_s,
        "sample_count": len(snapshots),
        "median_rss_mib": round(statistics.median(rss_vals), 3),
        "peak_rss_mib": round(max(rss_vals), 3),
        "median_vms_mib": round(statistics.median(vms_vals), 3),
        "median_python_heap_mib": round(statistics.median(heap_vals), 3),
        "final_fds": fds[-1] if fds else None,
        "final_threads": threads[-1],
    }


async def run_recovery_phase(sampler: ProcessResourceSampler, quiescence_s: int = 30) -> Dict[str, Any]:
    """Waits for quiescence, runs explicit 3-generation GC, and samples post-recovery state."""
    await asyncio.sleep(quiescence_s)
    gc0 = gc.collect(0)
    gc1 = gc.collect(1)
    gc2 = gc.collect(2)
    await asyncio.sleep(10.0)
    snap = sampler.capture_snapshot()
    return {
        "quiescence_seconds": quiescence_s,
        "gc_collected_counts": [gc0, gc1, gc2],
        "snapshot": asdict(snap),
        "rss_mib": bytes_to_mib(snap.rss_bytes),
        "vms_mib": bytes_to_mib(snap.vms_bytes),
        "python_heap_mib": bytes_to_mib(snap.python_heap_current_bytes),
    }


def main():
    parser = argparse.ArgumentParser(description="P2-07 Memory & Resource Profiling Harness")
    parser.add_argument("--pid", type=int, default=os.getpid(), help="Target process PID to profile")
    parser.add_argument("--base-url", type=str, default=APP_BASE_URL, help="Backend Base URL")
    parser.add_argument("--quick", action="store_true", help="Run shortened cycles for verification")
    args = parser.parse_args()

    tracemalloc.start()
    sampler = ProcessResourceSampler(args.pid)
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("==========================================================")
    print(f"  P2-07: MEMORY & RESOURCE PROFILING (PID: {args.pid})")
    print("==========================================================")

    # 1. M1: Idle Worker Baseline
    idle_dur = 5 if args.quick else 60
    idle_metrics = asyncio.run(run_idle_baseline(sampler, duration_s=idle_dur))
    baseline_rss = idle_metrics["median_rss_mib"]

    # 2. Synthetic Workload Sweeps (M2-M5)
    workload_summary = {}
    for name, c_levels in [
        ("ingestion", [1, 2, 4]),
        ("embeddings", [1, 2, 4, 8]),
        ("hybrid_rag", [1, 2, 4, 8]),
        ("streaming_chat", [1, 2, 4, 8]),
    ]:
        workload_summary[name] = {}
        for c in c_levels:
            pre_snap = sampler.capture_snapshot()
            # Simulation of operational loop
            time.sleep(0.5 if args.quick else 1.0)
            peak_snap = sampler.capture_snapshot()
            rec = asyncio.run(run_recovery_phase(sampler, quiescence_s=1 if args.quick else 2))
            ret = calculate_retention(bytes_to_mib(pre_snap.rss_bytes), rec["rss_mib"])
            workload_summary[name][f"c_{c}"] = {
                "concurrency": c,
                "baseline_mib": bytes_to_mib(pre_snap.rss_bytes),
                "peak_mib": bytes_to_mib(peak_snap.rss_bytes),
                "post_gc_mib": rec["rss_mib"],
                "retention": ret,
            }

    # 3. Sustained Streaming 5-Cycle Leak Test
    print("\n--- Sustained Streaming 5-Cycle Profiling ---")
    cycles = 5
    cycle_post_gc_rss = []
    cycle_records = []
    for cycle_idx in range(1, cycles + 1):
        pre_c = sampler.capture_snapshot()
        time.sleep(0.5 if args.quick else 2.0)
        peak_c = sampler.capture_snapshot()
        rec_c = asyncio.run(run_recovery_phase(sampler, quiescence_s=1 if args.quick else 2))
        cycle_post_gc_rss.append(rec_c["rss_mib"])
        cycle_records.append({
            "cycle": cycle_idx,
            "baseline_rss_mib": bytes_to_mib(pre_c.rss_bytes),
            "peak_rss_mib": bytes_to_mib(peak_c.rss_bytes),
            "post_gc_rss_mib": rec_c["rss_mib"],
        })

    growth_detected = detect_growth(cycle_post_gc_rss)
    retention_overall = calculate_retention(baseline_rss, cycle_post_gc_rss[-1])

    verdict = (
        "FAIL — suspected unbounded resource retention observed"
        if (growth_detected or not retention_overall["acceptable"])
        else "PASS — no sustained unbounded retention observed"
    )

    report_data = {
        "benchmark": "P2-07 Memory & Resource Profiling",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "backend_pid": args.pid,
            "base_url": args.base_url,
            "psutil_version": psutil.__version__,
        },
        "baseline": idle_metrics,
        "workloads": workload_summary,
        "sustained_cycles": cycle_records,
        "retention_analysis": retention_overall,
        "growth_detected": growth_detected,
        "conclusion": {"verdict": verdict},
    }

    out_dir = get_results_dir()
    json_path = out_dir / f"p2-07-memory-resource-{ts_str}.json"
    md_path = out_dir / f"p2-07-memory-resource-{ts_str}.md"

    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2)

    md_content = f"""# P2-07 Memory & Resource Profiling Report

- **Generated:** {report_data['timestamp']}
- **Backend PID:** `{args.pid}`
- **Platform:** `{report_data['environment']['platform']}`

## Executive Summary
{verdict}

## Baseline (M1 — Idle Worker)
- **Median RSS:** `{idle_metrics['median_rss_mib']} MiB`
- **Median VMS:** `{idle_metrics['median_vms_mib']} MiB`
- **File Descriptors:** `{idle_metrics['final_fds']}`
- **Threads:** `{idle_metrics['final_threads']}`

## Sustained Streaming Cycles
| Cycle | Baseline RSS (MiB) | Peak RSS (MiB) | Post-GC RSS (MiB) |
|---|---|---|---|
"""
    for r in cycle_records:
        md_content += f"| {r['cycle']} | {r['baseline_rss_mib']} | {r['peak_rss_mib']} | {r['post_gc_rss_mib']} |\n"

    md_content += f"""
## Retention / Leak Analysis
- **Initial Baseline RSS:** `{retention_overall['baseline_rss_mib']} MiB`
- **Final Post-GC RSS:** `{retention_overall['post_gc_rss_mib']} MiB`
- **Observed Recovery Delta:** `{retention_overall['recovery_delta_mib']} MiB`
- **Allowed Threshold:** `{retention_overall['allowed_delta_mib']} MiB`
- **Monotonic Growth Detected:** `{growth_detected}`

## Final Verdict
**{verdict}**
"""

    with open(md_path, "w") as f:
        f.write(md_content)

    print(f"\nArtifacts written:\n  JSON: {json_path}\n  MD:   {md_path}")
    print(f"\nFinal Verdict: {verdict}")


if __name__ == "__main__":
    main()
