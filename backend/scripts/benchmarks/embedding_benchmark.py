"""
P2-03 Embedding Throughput, Concurrency Scaling, and Capacity Characterization Benchmark.

Evaluates:
1. Concurrency scaling sweep: C in {1, 2, 4, 8, 16} with N=30, warmup=5
2. Batching characterization: B in {1, 4, 8, 16} using /api/embed
3. End-to-End Ingestion workload: Serial vs Bounded (C in {2, 4, 8}) at 100 & 500 chunks
"""

import asyncio
import datetime
import json
import os
import pathlib
import statistics
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.db.models import Chat, Document, DocumentChunk, User
from app.db.session import SessionLocal
from app.services.embedding_service import EmbeddingService


def get_or_create_bench_user(db):
    BENCH_EMAIL = "benchmark_runner_p203@example.com"
    user = db.query(User).filter(User.email == BENCH_EMAIL).first()
    created = False
    if not user:
        user = User(email=BENCH_EMAIL, hashed_password="fixture_dummy_hash", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        created = True
    return user, created

SAMPLE_PROMPT = "Retrieval-augmented generation pipelines depend on low-latency embedding throughput and efficient vector search."

RESULTS_DIR = pathlib.Path("/tmp/benchmark-results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


async def run_microbenchmark_sweep(
    concurrency_levels: List[int],
    n_requests: int = 30,
    warmup: int = 5,
) -> List[Dict[str, Any]]:
    base_url = settings.OLLAMA_BASE_URL
    model = getattr(settings, "OLLAMA_EMBED_MODEL", None) or "nomic-embed-text"
    endpoint = f"{base_url}/api/embeddings"

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Warmup
        for _ in range(warmup):
            await client.post(endpoint, json={"model": model, "prompt": SAMPLE_PROMPT})

        for c in concurrency_levels:
            sem = asyncio.Semaphore(c)
            latencies: List[float] = []
            errors = 0

            async def worker():
                nonlocal errors
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        resp = await client.post(endpoint, json={"model": model, "prompt": SAMPLE_PROMPT})
                        if resp.status_code == 200:
                            lat = (time.perf_counter() - t0) * 1000
                            latencies.append(lat)
                        else:
                            errors += 1
                    except Exception:
                        errors += 1

            wall_t0 = time.perf_counter()
            tasks = [worker() for _ in range(n_requests)]
            await asyncio.gather(*tasks)
            wall_duration = time.perf_counter() - wall_t0

            s = sorted(latencies) if latencies else [0.0]
            count = len(s)
            p50 = statistics.median(s)
            p95 = s[int(count * 0.95)] if count > 1 else s[0]
            p99 = s[int(count * 0.99)] if count > 1 else s[0]
            mean_lat = statistics.mean(s)
            throughput = count / wall_duration if wall_duration > 0 else 0.0

            results.append({
                "concurrency": c,
                "n_requests": n_requests,
                "successful": count,
                "errors": errors,
                "wall_clock_sec": round(wall_duration, 4),
                "throughput_emb_sec": round(throughput, 2),
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "p99_ms": round(p99, 2),
                "min_ms": round(s[0], 2),
                "max_ms": round(s[-1], 2),
                "mean_ms": round(mean_lat, 2),
            })
            print(f"[Micro C={c:2d}] p50={p50:6.2f}ms | p95={p95:6.2f}ms | throughput={throughput:5.2f} emb/s | errors={errors}")

    # Calculate speedup and efficiency relative to C=1
    baseline_tp = results[0]["throughput_emb_sec"] if results else 1.0
    for r in results:
        r["speedup"] = round(r["throughput_emb_sec"] / baseline_tp, 2) if baseline_tp > 0 else 1.0
        r["efficiency"] = round(r["speedup"] / r["concurrency"], 2)

    return results


async def run_batch_sweep(batch_sizes: List[int], total_items: int = 48) -> List[Dict[str, Any]]:
    base_url = settings.OLLAMA_BASE_URL
    model = getattr(settings, "OLLAMA_EMBED_MODEL", None) or "nomic-embed-text"
    endpoint = f"{base_url}/api/embed"

    results = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Warmup
        await client.post(endpoint, json={"model": model, "input": [SAMPLE_PROMPT]})

        for b in batch_sizes:
            iterations = max(1, total_items // b)
            batch_latencies = []
            errors = 0
            payload = [f"{SAMPLE_PROMPT} Chunk index {i}" for i in range(b)]

            wall_t0 = time.perf_counter()
            for _ in range(iterations):
                t0 = time.perf_counter()
                try:
                    resp = await client.post(endpoint, json={"model": model, "input": payload})
                    if resp.status_code == 200:
                        batch_latencies.append((time.perf_counter() - t0) * 1000)
                    else:
                        errors += 1
                except Exception:
                    errors += 1
            wall_duration = time.perf_counter() - wall_t0

            total_embeddings = iterations * b
            throughput = total_embeddings / wall_duration if wall_duration > 0 else 0.0
            avg_batch_lat = statistics.mean(batch_latencies) if batch_latencies else 0.0
            lat_per_chunk = avg_batch_lat / b if b > 0 else 0.0

            results.append({
                "batch_size": b,
                "iterations": iterations,
                "total_embeddings": total_embeddings,
                "errors": errors,
                "wall_clock_sec": round(wall_duration, 4),
                "throughput_emb_sec": round(throughput, 2),
                "batch_mean_ms": round(avg_batch_lat, 2),
                "per_chunk_effective_ms": round(lat_per_chunk, 2),
            })
            print(f"[Batch B={b:2d}] Throughput={throughput:5.2f} emb/s | batch_latency={avg_batch_lat:6.2f}ms | per_chunk={lat_per_chunk:5.2f}ms | errors={errors}")

    return results


async def run_e2e_ingestion_benchmark(chunk_counts: List[int]) -> List[Dict[str, Any]]:
    client = EmbeddingService.get_client()
    created_local = False
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=30.0)
        EmbeddingService.set_client(client)
        created_local = True

    results = []
    strategies = [
        ("serial", 1),
        ("bounded", 2),
        ("bounded", 4),
        ("bounded", 8),
    ]

    try:
        for n_chunks in chunk_counts:
            # Build fixed synthetic text for n_chunks
            chunks_text = [
                f"Synthetic chunk content paragraph {i} exploring retrieval-augmented systems vector search index."
                for i in range(n_chunks)
            ]

            for strat_name, concurrency in strategies:
                db = SessionLocal()
                bench_user, user_created = get_or_create_bench_user(db)
                chat = Chat(user_id=bench_user.id, title=f"Bench E2E {strat_name} C={concurrency} N={n_chunks}")
                db.add(chat)
                db.flush()

                doc = Document(
                    user_id=bench_user.id,
                    chat_id=chat.id,
                    filename=f"bench_{strat_name}_c{concurrency}_n{n_chunks}.pdf",
                    mime_type="application/pdf",
                    file_size=n_chunks * 100,
                    page_count=max(1, n_chunks // 10),
                    storage_url="local://bench",
                    status="processing",
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)

                errors = 0
                t0 = time.perf_counter()

                if strat_name == "serial":
                    for idx, txt in enumerate(chunks_text):
                        vec = await EmbeddingService.generate_embedding(txt, model_provider="ollama")
                        if vec:
                            db_chunk = DocumentChunk(
                                document_id=doc.id,
                                chat_id=chat.id,
                                chunk_index=idx,
                                page_number=1,
                                content=txt,
                                embedding=vec,
                            )
                            db.add(db_chunk)
                        else:
                            errors += 1
                    db.commit()

                elif strat_name == "bounded":
                    sem = asyncio.Semaphore(concurrency)

                    async def embed_and_persist(idx: int, txt: str):
                        nonlocal errors
                        async with sem:
                            vec = await EmbeddingService.generate_embedding(txt, model_provider="ollama")
                            if vec:
                                return DocumentChunk(
                                    document_id=doc.id,
                                    chat_id=chat.id,
                                    chunk_index=idx,
                                    page_number=1,
                                    content=txt,
                                    embedding=vec,
                                )
                            errors += 1
                            return None

                    tasks = [embed_and_persist(i, t) for i, t in enumerate(chunks_text)]
                    persisted_chunks = await asyncio.gather(*tasks)
                    for chk in persisted_chunks:
                        if chk is not None:
                            db.add(chk)
                    db.commit()

                wall_duration = time.perf_counter() - t0
                throughput = (n_chunks - errors) / wall_duration if wall_duration > 0 else 0.0

                results.append({
                    "workload_chunks": n_chunks,
                    "strategy": strat_name,
                    "concurrency": concurrency,
                    "duration_sec": round(wall_duration, 4),
                    "throughput_chunks_sec": round(throughput, 2),
                    "avg_ms_per_chunk": round((wall_duration / n_chunks) * 1000, 2),
                    "errors": errors,
                })

                print(f"[E2E N={n_chunks:3d} | {strat_name} C={concurrency}] duration={wall_duration:6.2f}s | throughput={throughput:5.2f} chk/s | errors={errors}")

                # Cleanup test records
                db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
                db.query(Document).filter(Document.id == doc.id).delete()
                db.query(Chat).filter(Chat.id == chat.id).delete()
                if user_created:
                    db.query(User).filter(User.id == bench_user.id).delete()
                db.commit()
                db.close()

    finally:
        if created_local:
            EmbeddingService.set_client(None)
            await client.aclose()

    return results


def export_artifacts(
    micro_res: List[Dict[str, Any]],
    batch_res: List[Dict[str, Any]],
    e2e_res: List[Dict[str, Any]],
) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"p2-03-embedding-{timestamp}.json"
    md_path = RESULTS_DIR / f"p2-03-embedding-{timestamp}.md"

    data = {
        "timestamp": timestamp,
        "microbenchmark": micro_res,
        "batch_benchmark": batch_res,
        "e2e_ingestion": e2e_res,
    }

    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    with open(md_path, "w") as f:
        f.write(f"# P2-03 Embedding Throughput & Capacity Characterization Report\n\n")
        f.write(f"Generated at: {timestamp} (UTC)\n\n")

        f.write("## 1. Embedding Microbenchmark Concurrency Sweep (N=30, Warmup=5)\n\n")
        f.write("| C | Successful | Errors | Wall (s) | Throughput (emb/s) | p50 (ms) | p95 (ms) | p99 (ms) | Speedup | Efficiency |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in micro_res:
            f.write(f"| {r['concurrency']} | {r['successful']} | {r['errors']} | {r['wall_clock_sec']} | {r['throughput_emb_sec']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} | {r['speedup']}x | {r['efficiency']} |\n")

        f.write("\n## 2. Ollama `/api/embed` Batch Mode Characterization\n\n")
        f.write("| Batch Size (B) | Iterations | Total Chunks | Wall (s) | Throughput (emb/s) | Batch Mean (ms) | Effective ms/chunk | Errors |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for b in batch_res:
            f.write(f"| {b['batch_size']} | {b['iterations']} | {b['total_embeddings']} | {b['wall_clock_sec']} | {b['throughput_emb_sec']} | {b['batch_mean_ms']} | {b['per_chunk_effective_ms']} | {b['errors']} |\n")

        f.write("\n## 3. End-to-End Ingestion Pipeline Benchmark\n\n")
        f.write("| Workload (Chunks) | Strategy | Concurrency | Duration (s) | Throughput (chk/s) | Avg ms/chunk | Errors |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for e in e2e_res:
            f.write(f"| {e['workload_chunks']} | {e['strategy']} | {e['concurrency']} | {e['duration_sec']} | {e['throughput_chunks_sec']} | {e['avg_ms_per_chunk']} | {e['errors']} |\n")

    print(f"\nSaved artifacts:")
    print(f"- {json_path}")
    print(f"- {md_path}")


async def main():
    print("==========================================================")
    print("   P2-03: EMBEDDING CAPACITY & THROUGHPUT CHARACTERIZATION")
    print("==========================================================")

    print("\n--- [Phase 1] Microbenchmark Sweep (C = 1, 2, 4, 8, 16) ---")
    micro_results = await run_microbenchmark_sweep([1, 2, 4, 8, 16], n_requests=30, warmup=5)

    print("\n--- [Phase 2] Batch API Sweep (B = 1, 4, 8, 16) ---")
    batch_results = await run_batch_sweep([1, 4, 8, 16], total_items=48)

    print("\n--- [Phase 3] E2E Ingestion Pipeline (100 & 500 Chunks) ---")
    e2e_results = await run_e2e_ingestion_benchmark([100, 500])

    print("\n--- [Phase 4] Artifact Generation ---")
    export_artifacts(micro_results, batch_results, e2e_results)


if __name__ == "__main__":
    asyncio.run(main())
