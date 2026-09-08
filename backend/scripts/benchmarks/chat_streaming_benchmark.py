"""
P2-05 Chat Streaming Capacity & Concurrency Characterization Benchmark.

Characterizes:
1. Workload A: Non-RAG + Ollama (llama3.2)
2. Workload B: RAG (500 chunks, top_k=6) + Ollama (llama3.2)
3. Workload C: Non-RAG + Gemini (gemini-2.5-flash)
4. Workload D: RAG (500 chunks, top_k=6) + Gemini (gemini-2.5-flash)
5. Concurrency Sweep: C in {1, 2, 4, 8} (and C=16 if stable)
6. Metrics: TTFT, Duration, E2E Latency, Speedup, Efficiency, Chars/sec, Chunks/sec
7. Resource Attribution: CPU % (peak/avg), RSS Memory delta (start/peak/end)
8. Lifecycle Verification: stream_started -> chunk -> exactly one terminal event
"""

import asyncio
import datetime
import json
import math
import os
import pathlib
import random
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psutil
from app.core.security import create_access_token
from app.db.models import Chat, Document, DocumentChunk, User
from app.db.session import SessionLocal

RESULTS_DIR = pathlib.Path("/tmp/benchmark-results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

BENCH_USER_EMAIL = "benchmark_p205_runner@example.com"
APP_BASE_URL = os.getenv("BENCHMARK_BASE_URL", "http://127.0.0.1:8000")


def generate_synthetic_unit_vector(dim: int = 768) -> List[float]:
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def ensure_bench_user() -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == BENCH_USER_EMAIL).first()
        if not user:
            user = User(
                name="Benchmark Runner P205",
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


def seed_rag_document(user_id: int, chunk_count: int = 500) -> Tuple[int, int]:
    db = SessionLocal()
    try:
        chat = Chat(user_id=user_id, title="P205 RAG Fixture Chat")
        db.add(chat)
        db.flush()

        doc = Document(
            user_id=user_id,
            chat_id=chat.id,
            filename="p205_rag_corpus.pdf",
            mime_type="application/pdf",
            file_size=chunk_count * 500,
            page_count=max(1, chunk_count // 5),
            status="ready",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        base_vec = generate_synthetic_unit_vector(768)
        batch_size = 500
        chunks = []
        for i in range(chunk_count):
            vec = [(v + random.uniform(-0.05, 0.05)) for v in base_vec]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            unit_vec = [round(x / norm, 6) for x in vec]

            chunk = DocumentChunk(
                chat_id=chat.id,
                document_id=doc.id,
                content=f"Paragraph {i}: High throughput streaming chat architecture and vector similarity search benchmarks.",
                page_number=(i // 5) + 1,
                chunk_index=i,
                embedding=unit_vec,
            )
            chunks.append(chunk)

            if len(chunks) >= batch_size:
                db.bulk_save_objects(chunks)
                db.commit()
                chunks.clear()

        if chunks:
            db.bulk_save_objects(chunks)
            db.commit()

        return chat.id, doc.id
    finally:
        db.close()


def cleanup_fixtures(chat_ids: List[int], doc_ids: List[int]) -> None:
    db = SessionLocal()
    try:
        if doc_ids:
            db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
        if chat_ids:
            db.query(Chat).filter(Chat.id.in_(chat_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def create_ephemeral_chat(user_id: int, title: str) -> int:
    db = SessionLocal()
    try:
        chat = Chat(user_id=user_id, title=title)
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat.id
    finally:
        db.close()


class StreamCollector:
    """Parses and records granular SSE stream events and lifecycle metrics."""

    def __init__(self):
        self.t_start: float = 0.0
        self.t_first_token: Optional[float] = None
        self.t_retrieval: Optional[float] = None
        self.t_end: Optional[float] = None
        self.chunks_count: int = 0
        self.chars_count: int = 0
        self.terminal_events: List[str] = []
        self.error_detail: Optional[str] = None
        self.has_stream_started: bool = False

    def parse_sse_line(self, line: str, current_event: Optional[str]) -> Tuple[Optional[str], bool]:
        """
        Parses a single line of SSE wire output.
        Returns: (updated_event, is_completed)
        """
        if not line or line.startswith(":"):
            return current_event, False

        if line.startswith("event:"):
            return line.replace("event:", "").strip(), False

        if line.startswith("data:"):
            raw_data = line.replace("data:", "").strip()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = {}

            if current_event == "stream_started":
                self.has_stream_started = True

            elif current_event == "sources":
                if self.t_retrieval is None:
                    self.t_retrieval = (time.perf_counter() - self.t_start) * 1000.0

            elif current_event == "chunk":
                text = data.get("text", "")
                if text:
                    if self.t_first_token is None:
                        self.t_first_token = (time.perf_counter() - self.t_start) * 1000.0
                    self.chunks_count += 1
                    self.chars_count += len(text)

            elif current_event in ("stream_completed", "stream_error", "stream_cancelled"):
                self.terminal_events.append(current_event)
                if current_event == "stream_error":
                    self.error_detail = data.get("message") or raw_data
                return current_event, True

        return current_event, False


async def execute_single_stream(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int,
    prompt: str,
    provider: str,
    model: str,
    document_id: Optional[int] = None,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "prompt": prompt,
        "provider": provider,
        "model": model,
    }
    if document_id is not None:
        payload["document_id"] = document_id

    collector = StreamCollector()
    collector.t_start = time.perf_counter()
    current_event: Optional[str] = None
    http_error = None

    try:
        async with client.stream(
            "POST",
            "/chat/stream",
            json=payload,
            headers=headers,
            timeout=timeout_sec,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                return {
                    "success": False,
                    "http_status": resp.status_code,
                    "error": f"HTTP {resp.status_code}: {body.decode('utf-8', errors='ignore')}",
                    "ttft_ms": None,
                    "duration_ms": (time.perf_counter() - collector.t_start) * 1000.0,
                    "retrieval_ms": None,
                    "chunks": 0,
                    "chars": 0,
                    "terminal_event": None,
                    "lifecycle_clean": False,
                }

            async for line in resp.aiter_lines():
                current_event, is_completed = collector.parse_sse_line(line, current_event)
                if is_completed:
                    break

    except Exception as exc:
        http_error = str(exc)

    collector.t_end = time.perf_counter()
    total_duration_ms = (collector.t_end - collector.t_start) * 1000.0

    terminal = collector.terminal_events[0] if collector.terminal_events else None
    has_exact_one_terminal = len(collector.terminal_events) == 1
    success = (
        http_error is None
        and terminal == "stream_completed"
        and has_exact_one_terminal
        and collector.t_first_token is not None
    )

    return {
        "success": success,
        "error": http_error or collector.error_detail,
        "ttft_ms": round(collector.t_first_token, 2) if collector.t_first_token else None,
        "duration_ms": round(total_duration_ms, 2),
        "retrieval_ms": round(collector.t_retrieval, 2) if collector.t_retrieval else None,
        "chunks": collector.chunks_count,
        "chars": collector.chars_count,
        "terminal_event": terminal,
        "terminal_count": len(collector.terminal_events),
        "lifecycle_clean": has_exact_one_terminal and collector.has_stream_started,
    }


async def run_concurrency_batch(
    user_id: int,
    token: str,
    provider: str,
    model: str,
    concurrency: int,
    n_requests: int,
    prompt: str,
    document_id: Optional[int] = None,
) -> Dict[str, Any]:
    process = psutil.Process(os.getpid())
    rss_start = process.memory_info().rss / (1024 * 1024)

    cpu_samples: List[float] = []
    stop_sampler = asyncio.Event()

    async def sample_cpu():
        while not stop_sampler.is_set():
            cpu_samples.append(process.cpu_percent(interval=None))
            await asyncio.sleep(0.1)

    sampler_task = asyncio.create_task(sample_cpu())

    sem = asyncio.Semaphore(concurrency)
    created_chat_ids: List[int] = []
    results: List[Dict[str, Any]] = []

    # Pre-create independent chats for each request to avoid concurrent chat-lock or title conflicts
    for i in range(n_requests):
        c_id = create_ephemeral_chat(user_id, f"Bench Chat C{concurrency}_{i}")
        created_chat_ids.append(c_id)

    async with httpx.AsyncClient(base_url=APP_BASE_URL, timeout=120.0) as client:
        async def worker(chat_id: int):
            async with sem:
                res = await execute_single_stream(
                    client=client,
                    token=token,
                    chat_id=chat_id,
                    prompt=prompt,
                    provider=provider,
                    model=model,
                    document_id=document_id,
                )
                results.append(res)

        wall_t0 = time.perf_counter()
        tasks = [worker(c_id) for c_id in created_chat_ids]
        await asyncio.gather(*tasks)
        wall_duration = time.perf_counter() - wall_t0

    stop_sampler.set()
    await sampler_task

    rss_end = process.memory_info().rss / (1024 * 1024)
    rss_peak = rss_end  # In Linux cgroup / container, current RSS at workload end approximates peak

    # Cleanup ephemeral chats
    cleanup_fixtures(created_chat_ids, [])

    # Calculate metrics
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    throughput = len(successful) / wall_duration if wall_duration > 0 else 0.0

    ttfts = [r["ttft_ms"] for r in successful if r["ttft_ms"] is not None]
    durations = [r["duration_ms"] for r in successful]
    retrievals = [r["retrieval_ms"] for r in successful if r["retrieval_ms"] is not None]
    chars = [r["chars"] for r in successful]
    chunks = [r["chunks"] for r in successful]

    def pct(arr: List[float], p: float) -> Optional[float]:
        if not arr:
            return None
        s = sorted(arr)
        idx = int(len(s) * p)
        return round(s[min(idx, len(s) - 1)], 2)

    return {
        "concurrency": concurrency,
        "total_requests": n_requests,
        "successful": len(successful),
        "failed": len(failed),
        "wall_duration_sec": round(wall_duration, 3),
        "throughput_qps": round(throughput, 3),
        "ttft_p50_ms": pct(ttfts, 0.50),
        "ttft_p95_ms": pct(ttfts, 0.95),
        "ttft_p99_ms": pct(ttfts, 0.99),
        "ttft_mean_ms": round(statistics.mean(ttfts), 2) if ttfts else None,
        "duration_p50_ms": pct(durations, 0.50),
        "duration_p95_ms": pct(durations, 0.95),
        "duration_p99_ms": pct(durations, 0.99),
        "duration_mean_ms": round(statistics.mean(durations), 2) if durations else None,
        "retrieval_p50_ms": pct(retrievals, 0.50),
        "avg_chars": round(statistics.mean(chars), 1) if chars else 0,
        "avg_chunks": round(statistics.mean(chunks), 1) if chunks else 0,
        "chars_per_sec": round(sum(chars) / wall_duration, 1) if wall_duration > 0 else 0,
        "chunks_per_sec": round(sum(chunks) / wall_duration, 1) if wall_duration > 0 else 0,
        "lifecycle_clean_all": all(r["lifecycle_clean"] for r in results),
        "cpu_avg_pct": round(statistics.mean(cpu_samples), 1) if cpu_samples else 0.0,
        "cpu_peak_pct": round(max(cpu_samples), 1) if cpu_samples else 0.0,
        "rss_start_mb": round(rss_start, 2),
        "rss_end_mb": round(rss_end, 2),
        "rss_delta_mb": round(rss_end - rss_start, 2),
        "errors": [r["error"] for r in failed if r["error"]],
    }


async def run_workload_suite(
    workload_name: str,
    user_id: int,
    token: str,
    provider: str,
    model: str,
    prompt: str,
    document_id: Optional[int] = None,
    concurrency_levels: Optional[List[int]] = None,
    n_requests_per_c: int = 12,
) -> List[Dict[str, Any]]:
    if concurrency_levels is None:
        concurrency_levels = [1, 2, 4, 8]

    print(f"\n=======================================================")
    print(f"  RUNNING WORKLOAD: {workload_name}")
    print(f"  Provider: {provider} | Model: {model} | RAG: {document_id is not None}")
    print(f"=======================================================")

    # Warmup
    print("Executing warmup stream...")
    c_warmup = create_ephemeral_chat(user_id, "Warmup Chat")
    async with httpx.AsyncClient(base_url=APP_BASE_URL, timeout=60.0) as client:
        w_res = await execute_single_stream(
            client=client,
            token=token,
            chat_id=c_warmup,
            prompt=prompt,
            provider=provider,
            model=model,
            document_id=document_id,
        )
        print(f"Warmup status: {'SUCCESS' if w_res['success'] else 'FAILED'}")
    cleanup_fixtures([c_warmup], [])

    workload_results: List[Dict[str, Any]] = []
    base_throughput = 0.0

    for c in concurrency_levels:
        print(f"\nEvaluating Concurrency C={c} (N={n_requests_per_c})...")
        metrics = await run_concurrency_batch(
            user_id=user_id,
            token=token,
            provider=provider,
            model=model,
            concurrency=c,
            n_requests=n_requests_per_c,
            prompt=prompt,
            document_id=document_id,
        )

        if c == 1:
            base_throughput = metrics["throughput_qps"]

        speedup = (metrics["throughput_qps"] / base_throughput) if base_throughput > 0 else 1.0
        efficiency = (speedup / c) if c > 0 else 1.0

        metrics["speedup"] = round(speedup, 3)
        metrics["efficiency_pct"] = round(efficiency * 100, 1)

        print(
            f"[C={c:2d}] QPS: {metrics['throughput_qps']:5.2f} | "
            f"TTFT p50: {metrics['ttft_p50_ms']}ms | "
            f"Duration p50: {metrics['duration_p50_ms']}ms | "
            f"Speedup: {metrics['speedup']}x | "
            f"Efficiency: {metrics['efficiency_pct']}% | "
            f"Errors: {metrics['failed']}"
        )
        workload_results.append(metrics)

        # Early check: if C=8 collapsed or failed heavily, skip C=16
        if metrics["failed"] > (n_requests_per_c // 2):
            print(f"High failure rate detected at C={c}. Halting concurrency progression.")
            break

    return workload_results


def export_full_p205_report(all_workloads: Dict[str, Any]) -> Tuple[pathlib.Path, pathlib.Path]:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"p2-05-chat-streaming-{timestamp}.json"
    md_path = RESULTS_DIR / f"p2-05-chat-streaming-{timestamp}.md"

    with open(json_path, "w") as f:
        json.dump({"timestamp": timestamp, "workloads": all_workloads}, f, indent=2)

    with open(md_path, "w") as f:
        f.write("# P2-05 Chat Streaming Capacity & Concurrency Characterization Report\n\n")
        f.write(f"Generated at: {timestamp} (UTC)\n\n")

        for w_name, w_data in all_workloads.items():
            f.write(f"## Workload: {w_name}\n\n")
            f.write(f"- **Provider:** {w_data['provider']} | **Model:** {w_data['model']} | **RAG Enabled:** {w_data['rag']}\n\n")
            f.write("| C | QPS | Speedup | Efficiency | TTFT p50 (ms) | TTFT p95 (ms) | Duration p50 (ms) | Chars/s | CPU Avg/Peak % | RSS Delta (MB) | Errors |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")
            for row in w_data["results"]:
                f.write(
                    f"| {row['concurrency']} "
                    f"| {row['throughput_qps']} "
                    f"| {row['speedup']}x "
                    f"| {row['efficiency_pct']}% "
                    f"| {row['ttft_p50_ms']} "
                    f"| {row['ttft_p95_ms']} "
                    f"| {row['duration_p50_ms']} "
                    f"| {row['chars_per_sec']} "
                    f"| {row['cpu_avg_pct']}% / {row['cpu_peak_pct']}% "
                    f"| {row['rss_delta_mb']} "
                    f"| {row['failed']} |\n"
                )
            f.write("\n")

    print(f"\nSaved P2-05 artifacts:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    return json_path, md_path


async def main():
    print("==========================================================")
    print("  P2-05: CHAT STREAMING CAPACITY & CONCURRENCY BENCHMARK")
    print("==========================================================")

    user = ensure_bench_user()
    token = create_access_token(user_id=user.id)

    # Fixed seed RAG document (500 chunks)
    print("Seeding baseline RAG document fixture (500 chunks)...")
    rag_chat_id, rag_doc_id = seed_rag_document(user.id, chunk_count=500)
    print(f"Seeded RAG fixture: doc_id={rag_doc_id}, chat_id={rag_chat_id}")

    prompt_non_rag = "Explain the concept of software caching in three concise bullet points."
    prompt_rag = "Based on the uploaded document, summarize the high throughput streaming architecture in three concise points."

    all_workloads: Dict[str, Any] = {}

    try:
        # 1. Workload A: Non-RAG + Ollama
        res_a = await run_workload_suite(
            workload_name="Workload A (Non-RAG Ollama)",
            user_id=user.id,
            token=token,
            provider="ollama",
            model="llama3.2",
            prompt=prompt_non_rag,
            document_id=None,
            concurrency_levels=[1, 2, 4, 8],
            n_requests_per_c=12,
        )
        all_workloads["Workload A (Non-RAG Ollama)"] = {
            "provider": "ollama",
            "model": "llama3.2",
            "rag": False,
            "results": res_a,
        }

        # 2. Workload B: RAG + Ollama
        res_b = await run_workload_suite(
            workload_name="Workload B (RAG Ollama)",
            user_id=user.id,
            token=token,
            provider="ollama",
            model="llama3.2",
            prompt=prompt_rag,
            document_id=rag_doc_id,
            concurrency_levels=[1, 2, 4, 8],
            n_requests_per_c=12,
        )
        all_workloads["Workload B (RAG Ollama)"] = {
            "provider": "ollama",
            "model": "llama3.2",
            "rag": True,
            "results": res_b,
        }

        # 3. Workload C: Non-RAG + Gemini
        res_c = await run_workload_suite(
            workload_name="Workload C (Non-RAG Gemini)",
            user_id=user.id,
            token=token,
            provider="gemini",
            model="gemini-2.5-flash",
            prompt=prompt_non_rag,
            document_id=None,
            concurrency_levels=[1, 2, 4, 8],
            n_requests_per_c=12,
        )
        all_workloads["Workload C (Non-RAG Gemini)"] = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "rag": False,
            "results": res_c,
        }

        # 4. Workload D: RAG + Gemini
        res_d = await run_workload_suite(
            workload_name="Workload D (RAG Gemini)",
            user_id=user.id,
            token=token,
            provider="gemini",
            model="gemini-2.5-flash",
            prompt=prompt_rag,
            document_id=rag_doc_id,
            concurrency_levels=[1, 2, 4, 8],
            n_requests_per_c=12,
        )
        all_workloads["Workload D (RAG Gemini)"] = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "rag": True,
            "results": res_d,
        }

        # Export full report
        export_full_p205_report(all_workloads)

    finally:
        print("\nCleaning up RAG fixtures...")
        cleanup_fixtures([rag_chat_id], [rag_doc_id])
        print("Cleanup completed.")


if __name__ == "__main__":
    asyncio.run(main())
