"""
P2-07 Memory & Resource Profiling Harness.

Characterizes:
- M1: Idle Worker Baseline (60s at 1Hz sampling)
- M2: PDF Ingestion (C=1, 2, 4 across 10, 50, 100 pages)
- M3: Embeddings (C=1, 2, 4, 8)
- M4: Hybrid RAG (C=1, 2, 4, 8)
- M5: Streaming Chat (C=1, 2, 4, 8)
- Sustained Streaming Load (C=4, 10 minutes continuous streaming with 1Hz sampling, 5 cycles)

Profiles: RSS, VMS, Python heap (tracemalloc), generational GC, FDs, threads, and observed CPU.
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

from app.core.config import settings
from app.core.security import create_access_token
from app.db.models import Chat, Document, DocumentChunk, User
from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService
from scripts.benchmarks.client import create_benchmark_client

BENCH_USER_EMAIL = "benchmark_p207_runner@example.com"
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


def discover_backend_pid() -> int:
    """Deterministically identifies the backend worker process or fails fast."""
    current_pid = os.getpid()
    candidates = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.pid == current_pid or p.pid == 1:
                continue
            cmd = " ".join(p.info["cmdline"] or [])
            if "multiprocessing.spawn" in cmd or "uvicorn" in cmd:
                candidates.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not candidates:
        raise RuntimeError("No backend worker process found. Specify target PID explicitly with --pid.")
    return max(candidates)


class ProcessResourceSampler:
    """Profiles process memory, FDs, threads, and CPU."""

    def __init__(self, pid: Optional[int] = None, is_in_process: bool = False):
        self.is_in_process = is_in_process
        self.pid = pid or os.getpid()
        try:
            self.process = psutil.Process(self.pid)
            self.process.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            raise RuntimeError(f"Target process PID {self.pid} not found")

    def capture_snapshot(self) -> MemorySnapshot:
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
    """Enforces strict 5-cycle monotonic upward trend evaluation."""
    if len(cycle_snapshots_rss) < 5:
        return False
    return all((cycle_snapshots_rss[i] - cycle_snapshots_rss[i - 1]) >= min_growth_step_mib for i in range(1, len(cycle_snapshots_rss)))


def get_results_dir() -> pathlib.Path:
    # Resolve project root benchmark-results across local workspace and docker mounts
    root_candidates = [
        pathlib.Path("/app/benchmark-results"),
        pathlib.Path("/benchmark-results"),
        pathlib.Path(__file__).resolve().parents[3] / "benchmark-results",
        pathlib.Path.cwd() / "benchmark-results",
    ]
    for p in root_candidates:
        if p.exists() and p.is_dir():
            return p
    # Default to repo root benchmark-results relative to scripts/benchmarks/
    fallback = pathlib.Path(__file__).resolve().parents[3] / "benchmark-results"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def ensure_bench_user() -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == BENCH_USER_EMAIL).first()
        if not user:
            user = User(
                name="Benchmark Runner P207",
                email=BENCH_USER_EMAIL,
                password="fixture_dummy_hash",
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
                    content=f"Paragraph {i}: Deep neural networks and embedding cache retrieval pipelines characterization.",
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


def build_text_pdf_bytes(page_count: int = 10) -> bytes:
    """Builds a structurally valid PDF with realistic text content per page."""
    header = b"%PDF-1.4\n"
    objects = []
    page_obj_ids = []

    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    base_obj_idx = 3
    for p in range(page_count):
        content_stream = (
            f"BT /F1 12 Tf 50 700 Td (Page {p+1}: High throughput characterization for distributed RAG systems) Tj ET"
        ).encode()
        stream_len = len(content_stream)

        content_obj_id = base_obj_idx
        page_obj_id = base_obj_idx + 1
        page_obj_ids.append(page_obj_id)
        base_obj_idx += 2

        objects.append(
            f"{content_obj_id} 0 obj\n<< /Length {stream_len} >>\nstream\n".encode()
            + content_stream
            + b"\nendstream\nendobj\n"
        )
        objects.append(
            f"{page_obj_id} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_obj_id} 0 R >>\nendobj\n".encode()
        )

    # Object 2: Pages container
    kids_str = " ".join([f"{pid} 0 R" for pid in page_obj_ids])
    pages_obj = f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {page_count} >>\nendobj\n".encode()
    objects.insert(1, pages_obj)

    xref_offset = len(header) + sum(len(o) for o in objects)
    total_objs = len(objects) + 1
    xref = [f"xref\n0 {total_objs}\n0000000000 65535 f \n".encode()]

    offset = len(header)
    for o in objects:
        xref.append(f"{offset:010d} 00000 n \n".encode())
        offset += len(o)

    trailer = f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
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
        "gc_collected": [gc0, gc1, gc2],
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


async def run_m2_ingestion(client: httpx.AsyncClient, headers: Dict[str, str], chat_id: int, concurrency: int, runs: int, pages: int) -> Dict[str, Any]:
    pdf_data = build_text_pdf_bytes(page_count=pages)
    semaphore = asyncio.Semaphore(concurrency)
    metrics = {"completed": 0, "errors": 0, "status_codes": []}

    async def single_upload(i: int):
        files = {"file": (f"bench_p207_{pages}p_{i}.pdf", pdf_data, "application/pdf")}
        async with semaphore:
            try:
                resp = await client.post(f"/chat/upload-pdf/{chat_id}", headers=headers, files=files, timeout=60.0)
                metrics["status_codes"].append(resp.status_code)
                if resp.status_code in (200, 201):
                    metrics["completed"] += 1
                else:
                    metrics["errors"] += 1
            except Exception as e:
                metrics["errors"] += 1
                metrics["status_codes"].append(str(e))

    await asyncio.gather(*[single_upload(i) for i in range(runs)])
    return metrics


async def run_m3_embeddings(concurrency: int, count: int) -> Dict[str, Any]:
    service = EmbeddingService()
    texts = [f"Performance characterization vector test {i} for memory allocation." for i in range(count)]
    semaphore = asyncio.Semaphore(concurrency)
    metrics = {"completed": 0, "errors": 0}

    async def single_embed(text: str):
        async with semaphore:
            try:
                emb = await service.generate_embedding(text)
                if emb:
                    metrics["completed"] += 1
                else:
                    metrics["errors"] += 1
            except Exception:
                metrics["errors"] += 1

    await asyncio.gather(*[single_embed(t) for t in texts])
    return metrics


async def run_m4_m5_streaming(
    client: httpx.AsyncClient, headers: Dict[str, str], chat_id: int, concurrency: int, count: int, is_rag: bool
) -> Dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    metrics = {"completed": 0, "errors": 0, "status_codes": []}

    async def single_stream(idx: int):
        payload = {
            "chat_id": chat_id,
            "message": f"Characterize streaming memory consumption cycle {idx}",
            "use_rag": is_rag,
            "provider": "ollama",
        }
        async with semaphore:
            try:
                async with client.stream("POST", "/chat/stream", headers=headers, json=payload, timeout=60.0) as resp:
                    metrics["status_codes"].append(resp.status_code)
                    if resp.status_code == 200:
                        metrics["completed"] += 1
                    else:
                        metrics["errors"] += 1
                    async for _ in resp.aiter_lines():
                        pass
            except Exception as e:
                metrics["errors"] += 1
                metrics["status_codes"].append(str(e))

    await asyncio.gather(*[single_stream(i) for i in range(count)])
    return metrics


async def run_sustained_streaming_10m(
    client: httpx.AsyncClient, headers: Dict[str, str], chat_id: int, sampler: ProcessResourceSampler, duration_s: int = 600
) -> Tuple[List[MemorySnapshot], Dict[str, Any]]:
    print(f"\n--- Sustained Streaming Workload: C=4 for {duration_s}s with 1Hz continuous sampling ---")
    start_time = time.time()
    end_time = start_time + duration_s
    snapshots: List[MemorySnapshot] = [sampler.capture_snapshot()]
    stats = {"completed": 0, "errors": 0}

    async def worker():
        while time.time() < end_time:
            payload = {"chat_id": chat_id, "message": "Sustained stream load test", "use_rag": False, "provider": "ollama"}
            try:
                async with client.stream("POST", "/chat/stream", headers=headers, json=payload, timeout=30.0) as resp:
                    if resp.status_code == 200:
                        stats["completed"] += 1
                    else:
                        stats["errors"] += 1
                    async for _ in resp.aiter_lines():
                        if time.time() >= end_time:
                            break
            except Exception:
                stats["errors"] += 1
            await asyncio.sleep(0.01)

    async def sampler_loop():
        while time.time() < end_time:
            await asyncio.sleep(1.0)
            if time.time() < end_time:
                snapshots.append(sampler.capture_snapshot())

    workers = [asyncio.create_task(worker()) for _ in range(4)]
    sampler_task = asyncio.create_task(sampler_loop())

    await asyncio.gather(*workers, sampler_task)
    return snapshots, stats


def main():
    parser = argparse.ArgumentParser(description="P2-07 Memory & Resource Profiling Harness")
    parser.add_argument("--pid", type=int, default=None, help="Target backend process PID")
    parser.add_argument("--base-url", type=str, default=APP_BASE_URL, help="Backend Base URL")
    parser.add_argument("--transport", type=str, choices=["asgi", "http"], default="http", help="Client transport mode")
    parser.add_argument("--quick", action="store_true", help="Quick mode for CI smoke validation")
    args = parser.parse_args()

    # PID & Sampler Resolution
    target_pid = args.pid or (os.getpid() if args.transport == "asgi" else discover_backend_pid())
    sampler = ProcessResourceSampler(target_pid, is_in_process=(args.transport == "asgi"))
    tracemalloc.start()

    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print("==========================================================")
    print(f"  P2-07: MEMORY & RESOURCE PROFILING (Target PID: {target_pid}, Mode: {args.transport})")
    print("==========================================================")

    user = ensure_bench_user()
    token = create_access_token(user_id=user.id)
    auth_headers = {"Authorization": f"Bearer {token}"}
    chat_id, doc_id = seed_rag_fixture(user.id, chunk_count=500)

    # 1. M1: Idle Baseline
    idle_s = 5 if args.quick else 60
    idle_metrics = asyncio.run(run_idle_baseline(sampler, duration_s=idle_s))
    baseline_rss = idle_metrics["median_rss_mib"]

    workload_results = {}

    async def execute_benchmarks():
        async with create_benchmark_client(base_url=args.base_url, transport_mode=args.transport, timeout=90.0) as client:
            quiesce_s = 2 if args.quick else 30

            # M2: PDF Ingestion
            print("\n--- M2: PDF Ingestion (10, 50, 100 pages, C=1, 2, 4) ---")
            workload_results["m2_ingestion"] = {}
            for pages in ([10] if args.quick else [10, 50, 100]):
                for c in [1, 2, 4]:
                    pre = sampler.capture_snapshot()
                    runs = 2 if args.quick else 4
                    stats = await run_m2_ingestion(client, auth_headers, chat_id, concurrency=c, runs=runs, pages=pages)
                    peak = sampler.capture_snapshot()
                    rec = await run_recovery_phase(sampler, quiescence_s=quiesce_s)
                    workload_results["m2_ingestion"][f"p{pages}_c{c}"] = {
                        "pages": pages,
                        "concurrency": c,
                        "stats": stats,
                        "baseline_rss_mib": bytes_to_mib(pre.rss_bytes),
                        "peak_rss_mib": bytes_to_mib(peak.rss_bytes),
                        "post_gc_rss_mib": rec["rss_mib"],
                        "retention": calculate_retention(bytes_to_mib(pre.rss_bytes), rec["rss_mib"]),
                    }

            # M3: Embeddings
            print("\n--- M3: Embeddings (C=1, 2, 4, 8) ---")
            workload_results["m3_embeddings"] = {}
            for c in [1, 2, 4, 8]:
                pre = sampler.capture_snapshot()
                count = 4 if args.quick else 20
                stats = await run_m3_embeddings(concurrency=c, count=count)
                peak = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_s)
                workload_results["m3_embeddings"][f"c{c}"] = {
                    "concurrency": c,
                    "stats": stats,
                    "baseline_rss_mib": bytes_to_mib(pre.rss_bytes),
                    "peak_rss_mib": bytes_to_mib(peak.rss_bytes),
                    "post_gc_rss_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre.rss_bytes), rec["rss_mib"]),
                }

            # M4: Hybrid RAG
            print("\n--- M4: Hybrid RAG (C=1, 2, 4, 8) ---")
            workload_results["m4_hybrid_rag"] = {}
            for c in [1, 2, 4, 8]:
                pre = sampler.capture_snapshot()
                count = 3 if args.quick else 12
                stats = await run_m4_m5_streaming(client, auth_headers, chat_id, concurrency=c, count=count, is_rag=True)
                peak = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_s)
                workload_results["m4_hybrid_rag"][f"c{c}"] = {
                    "concurrency": c,
                    "stats": stats,
                    "baseline_rss_mib": bytes_to_mib(pre.rss_bytes),
                    "peak_rss_mib": bytes_to_mib(peak.rss_bytes),
                    "post_gc_rss_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre.rss_bytes), rec["rss_mib"]),
                }

            # M5: Streaming Chat
            print("\n--- M5: Streaming Chat (C=1, 2, 4, 8) ---")
            workload_results["m5_streaming"] = {}
            for c in [1, 2, 4, 8]:
                pre = sampler.capture_snapshot()
                count = 3 if args.quick else 12
                stats = await run_m4_m5_streaming(client, auth_headers, chat_id, concurrency=c, count=count, is_rag=False)
                peak = sampler.capture_snapshot()
                rec = await run_recovery_phase(sampler, quiescence_s=quiesce_s)
                workload_results["m5_streaming"][f"c{c}"] = {
                    "concurrency": c,
                    "stats": stats,
                    "baseline_rss_mib": bytes_to_mib(pre.rss_bytes),
                    "peak_rss_mib": bytes_to_mib(peak.rss_bytes),
                    "post_gc_rss_mib": rec["rss_mib"],
                    "retention": calculate_retention(bytes_to_mib(pre.rss_bytes), rec["rss_mib"]),
                }

            # Sustained Streaming Load (10 Minutes, C=4)
            sustained_dur = 10 if args.quick else 600
            sustained_samples, sustained_stats = await run_sustained_streaming_10m(
                client, auth_headers, chat_id, sampler, duration_s=sustained_dur
            )

            # 5-Cycle Leak Assessment (C=4)
            print("\n--- Sustained Streaming 5-Cycle Recovery Assessment ---")
            cycle_post_gc_rss = []
            cycle_records = []
            for cycle_idx in range(1, 6):
                pre_c = sampler.capture_snapshot()
                count_c = 4 if args.quick else 15
                await run_m4_m5_streaming(client, auth_headers, chat_id, concurrency=4, count=count_c, is_rag=False)
                peak_c = sampler.capture_snapshot()
                rec_c = await run_recovery_phase(sampler, quiescence_s=quiesce_s)
                cycle_post_gc_rss.append(rec_c["rss_mib"])
                cycle_records.append({
                    "cycle": cycle_idx,
                    "baseline_rss_mib": bytes_to_mib(pre_c.rss_bytes),
                    "peak_rss_mib": bytes_to_mib(peak_c.rss_bytes),
                    "post_gc_rss_mib": rec_c["rss_mib"],
                })

            return sustained_samples, sustained_stats, cycle_records, cycle_post_gc_rss

    sustained_samples, sustained_stats, cycle_records, cycle_post_gc_rss = asyncio.run(execute_benchmarks())

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
            "target_pid": target_pid,
            "transport_mode": args.transport,
            "base_url": args.base_url,
        },
        "baseline_m1": idle_metrics,
        "workloads": workload_results,
        "sustained_10m": {
            "duration_s": len(sustained_samples),
            "stats": sustained_stats,
            "peak_rss_mib": max([bytes_to_mib(s.rss_bytes) for s in sustained_samples]) if sustained_samples else baseline_rss,
        },
        "sustained_5_cycles": cycle_records,
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
- **Target Process PID:** `{target_pid}`
- **Transport Mode:** `{args.transport}`
- **Platform:** `{report_data['environment']['platform']}`

## Executive Summary
**{verdict}**

## 1. Baseline (M1 — Idle Worker)
- **Median RSS:** `{idle_metrics['median_rss_mib']} MiB`
- **Median VMS:** `{idle_metrics['median_vms_mib']} MiB`
- **File Descriptors:** `{idle_metrics['final_fds']}`
- **Threads:** `{idle_metrics['final_threads']}`

## 2. Sustained Streaming 10-Minute Characterization (C=4)
- **Duration Observed:** `{report_data['sustained_10m']['duration_s']}s`
- **Completed Requests:** `{sustained_stats['completed']}`
- **Failed Requests:** `{sustained_stats['errors']}`
- **Peak RSS Observed:** `{report_data['sustained_10m']['peak_rss_mib']} MiB`

## 3. Sustained 5-Cycle Leak Assessment (C=4)
| Cycle | Baseline RSS (MiB) | Peak RSS (MiB) | Post-GC RSS (MiB) |
|---|---|---|---|
"""
    for r in cycle_records:
        md_content += f"| {r['cycle']} | {r['baseline_rss_mib']} | {r['peak_rss_mib']} | {r['post_gc_rss_mib']} |\n"

    md_content += f"""
## 4. Retention & Leak Analysis
- **Initial Baseline RSS:** `{retention_overall['baseline_rss_mib']} MiB`
- **Final Post-GC RSS:** `{retention_overall['post_gc_rss_mib']} MiB`
- **Observed Recovery Delta:** `{retention_overall['recovery_delta_mib']} MiB`
- **Allowed Threshold:** `{retention_overall['allowed_delta_mib']} MiB`
- **Strict 5-Cycle Monotonic Growth:** `{growth_detected}`

## 5. Final Verdict
**{verdict}**
"""

    with open(md_path, "w") as f:
        f.write(md_content)

    print(f"\nArtifacts written:\n  JSON: {json_path}\n  MD:   {md_path}")
    print(f"\nFinal Verdict: {verdict}")


if __name__ == "__main__":
    main()
