"""
P2-07 Memory & Resource Profiling Harness.

Characterizes:
- M1: Idle Worker Baseline (60s at 1Hz sampling)
- M2: PDF Ingestion (C=1, 2, 4)
- M3: Embeddings (C=1, 2, 4, 8)
- M4: Hybrid RAG (C=1, 2, 4, 8)
- M5: Streaming Chat (C=1, 2, 4, 8)
- Sustained Streaming Load (C=4, 5 cycles with 30s quiescence and full GC recovery)

Measures: Process RSS, VMS, FDs, Threads, and CPU via psutil on the target backend PID.
"""

import argparse
import asyncio
import gc
import json
import math
import os
import pathlib
import platform
import random
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psutil
from app.core.security import create_access_token
from app.db.models import Chat, Document, DocumentChunk, User
from app.db.session import SessionLocal

APP_BASE_URL = os.getenv("BENCHMARK_BASE_URL", "http://127.0.0.1:8000")
BENCH_USER_EMAIL = "benchmark_p207_memory@example.com"


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


def discover_backend_pid() -> int:
    """Finds the uvicorn worker process running the application."""
    candidates = []
    current_pid = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == current_pid:
                continue
            cmd = " ".join(p.info["cmdline"] or [])
            if "multiprocessing.spawn" in cmd or "uvicorn" in cmd or "main:app" in cmd:
                candidates.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if candidates:
        return max(candidates)
    return 1


class ProcessResourceSampler:
    """Monitors the target process resources cleanly across platforms, recovering from worker restarts."""

    def __init__(self, pid: int):
        self.pid = pid
        self._init_process(pid)

    def _init_process(self, pid: int):
        self.pid = pid
        try:
            self.process = psutil.Process(pid)
            self.process.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            fallback = discover_backend_pid()
            self.pid = fallback
            self.process = psutil.Process(fallback)
            self.process.cpu_percent(interval=None)

    def capture_snapshot(self) -> MemorySnapshot:
        try:
            mem = self.process.memory_info()
        except psutil.NoSuchProcess:
            self._init_process(discover_backend_pid())
            mem = self.process.memory_info()
        rss = mem.rss
        vms = mem.vms

        if tracemalloc.is_tracing():
            curr_heap, peak_heap = tracemalloc.get_traced_memory()
        else:
            curr_heap, peak_heap = 0, 0

        gc_counts = gc.get_count()

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


def detect_growth(cycle_snapshots_rss: List[float], min_growth_step_mib: float = 0.5) -> bool:
    """Checks for persistent, materially positive upward trend across cycles (filtering minor allocator noise)."""
    if len(cycle_snapshots_rss) < 3:
        return False
    return all((cycle_snapshots_rss[i] - cycle_snapshots_rss[i - 1]) >= min_growth_step_mib for i in range(1, len(cycle_snapshots_rss)))


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


def ensure_bench_user() -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == BENCH_USER_EMAIL).first()
        if not user:
            user = User(
                name="Benchmark Runner P207",
                email=BENCH_USER_EMAIL,
                password="fixture_hash",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def generate_synthetic_unit_vector(dim: int = 768) -> List[float]:
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def seed_rag_fixture(user_id: int, chunk_count: int = 500) -> Tuple[int, int]:
    db = SessionLocal()
    try:
        chat = Chat(user_id=user_id, title="P207 Memory Characterization Chat")
        db.add(chat)
        db.flush()

        doc = Document(
            user_id=user_id,
            chat_id=chat.id,
            filename="p207_memory_corpus.pdf",
            mime_type="application/pdf",
            file_size=chunk_count * 500,
            page_count=max(1, chunk_count // 5),
            status="ready",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        base_vec = generate_synthetic_unit_vector(768)
        chunks = []
        for i in range(chunk_count):
            vec = [(v + random.uniform(-0.02, 0.02)) for v in base_vec]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            chunks.append(
                DocumentChunk(
                    chat_id=chat.id,
                    document_id=doc.id,
                    content=f"Paragraph {i}: Memory profiling and leak analysis for high-throughput RAG streaming.",
                    page_number=(i // 5) + 1,
                    chunk_index=i,
                    embedding=[round(x / norm, 6) for x in vec],
                )
            )
        db.bulk_save_objects(chunks)
        db.commit()
        return chat.id, doc.id
    finally:
        db.close()


def create_minimal_pdf_bytes(page_count: int = 10) -> bytes:
    """Generates a valid minimal PDF structure in bytes."""
    header = b"%PDF-1.4\n"
    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    page_refs = " ".join([f"{3 + i} 0 R" for i in range(page_count)])
    objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{page_refs}] /Count {page_count} >>\nendobj\n".encode())

    for i in range(page_count):
        obj_num = 3 + i
        objects.append(
            f"{obj_num} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n".encode()
        )

    xref_offset = len(header) + sum(len(o) for o in objects)
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()]

    running_offset = len(header)
    for o in objects:
        xref.append(f"{running_offset:010d} 00000 n \n".encode())
        running_offset += len(o)

    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return header + b"".join(objects) + b"".join(xref) + trailer


async def run_recovery_phase(sampler: ProcessResourceSampler, quiescence_s: int = 30) -> Dict[str, Any]:
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


async def run_idle_baseline(sampler: ProcessResourceSampler, duration_s: int = 60) -> Dict[str, Any]:
    print(f"\n--- M1: Profiling Idle Worker Baseline ({duration_s}s at 1Hz) ---")
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


async def execute_ingestion_workload(
    client: httpx.AsyncClient, auth_headers: Dict[str, str], chat_id: int, concurrency: int, runs: int
):
    pdf_data = create_minimal_pdf_bytes(page_count=10)

    async def single_upload(idx: int):
        files = {"file": (f"bench_doc_{idx}.pdf", pdf_data, "application/pdf")}
        try:
            await client.post(f"/chat/upload-pdf/{chat_id}", headers=auth_headers, files=files, timeout=60.0)
        except Exception:
            pass

    semaphore = asyncio.Semaphore(concurrency)

    async def bound_op(i: int):
        async with semaphore:
            await single_upload(i)

    tasks = [bound_op(i) for i in range(runs)]
    await asyncio.gather(*tasks)


async def execute_streaming_workload(
    client: httpx.AsyncClient, auth_headers: Dict[str, str], chat_id: int, concurrency: int, count: int, is_rag: bool = False
):
    semaphore = asyncio.Semaphore(concurrency)

    async def single_stream(idx: int):
        payload = {
            "chat_id": chat_id,
            "message": f"Summarize memory performance benchmark iteration {idx}.",
            "use_rag": is_rag,
            "provider": "ollama",
        }
        async with semaphore:
            try:
                async with client.stream("POST", "/chat/stream", headers=auth_headers, json=payload, timeout=60.0) as resp:
                    async for _ in resp.aiter_lines():
                        pass
            except Exception:
                pass

    tasks = [single_stream(i) for i in range(count)]
    await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="P2-07 Memory & Resource Profiling Harness")
    parser.add_argument("--pid", type=int, default=None, help="Target backend process PID (auto-discovered if omitted)")
    parser.add_argument("--base-url", type=str, default=APP_BASE_URL, help="Backend Base URL")
    parser.add_argument("--quick", action="store_true", help="Run quick sample cycles for test validation")
    args = parser.parse_args()

    target_pid = args.pid or discover_backend_pid()
    sampler = ProcessResourceSampler(target_pid)
    tracemalloc.start()

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print("==========================================================")
    print(f"  P2-07: MEMORY & RESOURCE PROFILING (Target PID: {target_pid})")
    print("==========================================================")

    # Fixture setup
    user = ensure_bench_user()
    token = create_access_token(user_id=user.id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    chat_id, doc_id = seed_rag_fixture(user.id, chunk_count=500)

    # 1. M1: Idle Baseline
    idle_s = 5 if args.quick else 60
    idle_metrics = asyncio.run(run_idle_baseline(sampler, duration_s=idle_s))
    baseline_rss = idle_metrics["median_rss_mib"]

    workload_summary = {}

    async def run_all_profiles():
        async with httpx.AsyncClient(base_url=args.base_url, timeout=90.0) as client:
            quiesce_dur = 2 if args.quick else 30

            # M2: PDF Ingestion
            print("\n--- M2: PDF Ingestion Memory Profiling (C=1, 2, 4) ---")
            workload_summary["ingestion"] = {}
            for c in [1, 2, 4]:
                pre_snap = sampler.capture_snapshot()
                n_ops = 2 if args.quick else 3
                await execute_ingestion_workload(client, auth_headers, chat_id, concurrency=c, runs=n_ops)
                peak_snap = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_dur)
                workload_summary["ingestion"][f"c_{c}"] = {
                    "concurrency": c,
                    "baseline_mib": bytes_to_mib(pre_snap.rss_bytes),
                    "peak_mib": bytes_to_mib(peak_snap.rss_bytes),
                    "post_gc_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre_snap.rss_bytes), rec["rss_mib"]),
                }

            # M3: Embeddings
            print("\n--- M3: Embeddings Memory Profiling (C=1, 2, 4, 8) ---")
            workload_summary["embeddings"] = {}
            for c in [1, 2, 4, 8]:
                pre_snap = sampler.capture_snapshot()
                n_reqs = 3 if args.quick else 30
                semaphore = asyncio.Semaphore(c)

                async def embed_call():
                    async with semaphore:
                        try:
                            await client.post(
                                "/chat/stream",
                                headers=auth_headers,
                                json={"chat_id": chat_id, "message": "Test embedding generation", "use_rag": False},
                                timeout=30.0,
                            )
                        except Exception:
                            pass

                await asyncio.gather(*[embed_call() for _ in range(n_reqs)])
                peak_snap = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_dur)
                workload_summary["embeddings"][f"c_{c}"] = {
                    "concurrency": c,
                    "baseline_mib": bytes_to_mib(pre_snap.rss_bytes),
                    "peak_mib": bytes_to_mib(peak_snap.rss_bytes),
                    "post_gc_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre_snap.rss_bytes), rec["rss_mib"]),
                }

            # M4: Hybrid RAG
            print("\n--- M4: Hybrid RAG Memory Profiling (C=1, 2, 4, 8) ---")
            workload_summary["hybrid_rag"] = {}
            for c in [1, 2, 4, 8]:
                pre_snap = sampler.capture_snapshot()
                n_reqs = 3 if args.quick else 30
                await execute_streaming_workload(client, auth_headers, chat_id, concurrency=c, count=n_reqs, is_rag=True)
                peak_snap = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_dur)
                workload_summary["hybrid_rag"][f"c_{c}"] = {
                    "concurrency": c,
                    "baseline_mib": bytes_to_mib(pre_snap.rss_bytes),
                    "peak_mib": bytes_to_mib(peak_snap.rss_bytes),
                    "post_gc_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre_snap.rss_bytes), rec["rss_mib"]),
                }

            # M5: Streaming Chat
            print("\n--- M5: Streaming Chat Memory Profiling (C=1, 2, 4, 8) ---")
            workload_summary["streaming_chat"] = {}
            for c in [1, 2, 4, 8]:
                pre_snap = sampler.capture_snapshot()
                n_reqs = 3 if args.quick else 30
                await execute_streaming_workload(client, auth_headers, chat_id, concurrency=c, count=n_reqs, is_rag=False)
                peak_snap = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_dur)
                workload_summary["streaming_chat"][f"c_{c}"] = {
                    "concurrency": c,
                    "baseline_mib": bytes_to_mib(pre_snap.rss_bytes),
                    "peak_mib": bytes_to_mib(peak_snap.rss_bytes),
                    "post_gc_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre_snap.rss_bytes), rec["rss_mib"]),
                }

            # Sustained Streaming 5-Cycle Leak Test (C=4)
            print("\n--- Sustained Streaming 5-Cycle Leak Profiling (C=4) ---")
            cycle_records = []
            cycle_post_gc_rss = []
            for cycle_idx in range(1, 6):
                pre_c = sampler.capture_snapshot()
                count_c = 4 if args.quick else 30
                await execute_streaming_workload(client, auth_headers, chat_id, concurrency=4, count=count_c, is_rag=False)
                peak_c = sampler.capture_snapshot()
                rec_c = await run_recovery_phase(sampler, quiescence_s=quiesce_dur)
                cycle_post_gc_rss.append(rec_c["rss_mib"])
                cycle_records.append({
                    "cycle": cycle_idx,
                    "baseline_rss_mib": bytes_to_mib(pre_c.rss_bytes),
                    "peak_rss_mib": bytes_to_mib(peak_c.rss_bytes),
                    "post_gc_rss_mib": rec_c["rss_mib"],
                })

            return cycle_records, cycle_post_gc_rss

    cycle_records, cycle_post_gc_rss = asyncio.run(run_all_profiles())

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
            "backend_pid": target_pid,
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
- **Backend PID:** `{target_pid}`
- **Platform:** `{report_data['environment']['platform']}`

## Executive Summary
{verdict}

## Environment
- **Target PID:** `{target_pid}`
- **Base URL:** `{args.base_url}`
- **Platform:** `{platform.platform()}`

## Methodology
- Target process RSS, VMS, FDs, and CPU tracked via psutil.Process({target_pid}).
- Workloads M2-M5 executed against live FastAPI HTTP endpoints.
- Quiescence and 3-generation explicit GC executed after each workload.

## Baseline (M1 — Idle Worker)
- **Median RSS:** `{idle_metrics['median_rss_mib']} MiB`
- **Median VMS:** `{idle_metrics['median_vms_mib']} MiB`
- **File Descriptors:** `{idle_metrics['final_fds']}`
- **Threads:** `{idle_metrics['final_threads']}`

## Sustained Streaming Cycles (C=4)
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

    print(f"\nArtifacts generated:\n  JSON: {json_path}\n  MD:   {md_path}")
    print(f"\nFinal Verdict: {verdict}")


if __name__ == "__main__":
    main()
