import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .auth import get_authenticated_headers
from .client import create_benchmark_client
from .config import BenchmarkConfig
from .metrics import ScenarioResult
from .scenarios import benchmark_health_live, benchmark_chat_non_rag, benchmark_chat_rag
from .seed_rag import seed_rag_document
from .system_metrics import ProcessSampler


def render_markdown(results: List[dict], timestamp: str) -> str:
    md = [
        f"# Performance Baseline Report — {timestamp}",
        "",
        "| Scenario | Concurrency | Iterations | Latency p50 (ms) | Retrieval p50 (ms) | TTFT p50 (ms) | Chunks/sec | Errors |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in results:
        m = r["metrics"]["latency_ms"]
        retrieval = r["metrics"].get("retrieval_ms")
        ttft = r["metrics"].get("ttft_ms")
        rates = r["metrics"].get("streaming_rates")
        retrieval_p50 = f"{retrieval['p50']}" if retrieval else "N/A"
        ttft_p50 = f"{ttft['p50']}" if ttft else "N/A"
        chunks_sec = f"{rates['chunks_per_sec']}" if rates else "N/A"
        md.append(
            f"| `{r['scenario']}` | {r['concurrency']} | {r['iterations']} | "
            f"{m['p50']} | {retrieval_p50} | {ttft_p50} | {chunks_sec} | {r['errors']} |"
        )
    md.append("")
    return "\n".join(md)


async def run_scenario(
    scenario_name: str,
    config: BenchmarkConfig,
    warmup: int,
    chunks: int = 50,
) -> ScenarioResult:
    scenario_label = f"{scenario_name}_{chunks}chunks" if scenario_name == "chat_rag" else scenario_name
    result = ScenarioResult(
        scenario=scenario_label,
        iterations=config.iterations,
        concurrency=config.concurrency,
        transport=config.transport,
    )
    sampler = ProcessSampler()

    async with create_benchmark_client(config.base_url, config.transport) as client:
        headers = {}
        chat_id = 0
        document_id = None

        if scenario_name != "health_live":
            print("Bootstrapping benchmark session...")
            headers = await get_authenticated_headers(client)

            if scenario_name == "chat_non_rag":
                chat_resp = await client.post("/chat/new", json={"title": "Benchmark Non-RAG Session"}, headers=headers)
                if chat_resp.status_code == 200:
                    chat_id = int(chat_resp.json().get("id", 0))
                else:
                    raise RuntimeError(f"Failed to create chat: {chat_resp.status_code} {chat_resp.text}")

            elif scenario_name == "chat_rag":
                print(f"Ensuring RAG corpus exists with {chunks} chunks...")
                chat_id, document_id = seed_rag_document(chunks)

        if warmup > 0:
            print(f"Running {warmup} warmup iterations (excluded from reported percentiles)...")
            warmup_res = ScenarioResult(scenario="warmup", iterations=warmup, concurrency=1, transport=config.transport)
            for _ in range(warmup):
                if scenario_name == "health_live":
                    await benchmark_health_live(client, warmup_res, headers=headers)
                elif scenario_name == "chat_non_rag":
                    await benchmark_chat_non_rag(client, warmup_res, headers=headers, chat_id=chat_id)
                elif scenario_name == "chat_rag":
                    await benchmark_chat_rag(client, warmup_res, headers=headers, chat_id=chat_id, document_id=document_id)

        print(f"Executing {config.iterations} measurement iterations (concurrency={config.concurrency})...")
        sem = asyncio.Semaphore(config.concurrency)

        async def worker():
            async with sem:
                if scenario_name == "health_live":
                    await benchmark_health_live(client, result, headers=headers)
                elif scenario_name == "chat_non_rag":
                    await benchmark_chat_non_rag(client, result, headers=headers, chat_id=chat_id)
                elif scenario_name == "chat_rag":
                    await benchmark_chat_rag(client, result, headers=headers, chat_id=chat_id, document_id=document_id)
                cpu, rss = sampler.sample()
                result.cpu_percent.append(cpu)
                result.rss_mb.append(rss)

        tasks = [asyncio.create_task(worker()) for _ in range(config.iterations)]
        await asyncio.gather(*tasks)

    return result


def main():
    parser = argparse.ArgumentParser(description="AI Engine Benchmark Harness")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of backend")
    parser.add_argument("--iterations", type=int, default=5, help="Total measurement iterations")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup iterations")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent requests")
    parser.add_argument("--transport", choices=["http", "asgi"], default="http", help="Runner transport mode")
    parser.add_argument("--scenario", default="health_live", choices=["health_live", "chat_non_rag", "chat_rag"], help="Scenario")
    parser.add_argument("--chunks", type=int, default=50, choices=[50, 500, 5000], help="RAG chunk corpus size")
    parser.add_argument("--out-dir", default="benchmark-results", help="Directory for report output")
    args = parser.parse_args()

    config = BenchmarkConfig(
        base_url=args.url,
        iterations=args.iterations,
        concurrency=args.concurrency,
        transport=args.transport,
        output_dir=args.out_dir,
    )

    res = asyncio.run(run_scenario(args.scenario, config, args.warmup, chunks=args.chunks))
    summary = res.summary()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(config.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / f"p2-01-{res.scenario}-{ts}.json"
    md_file = out_path / f"p2-01-{res.scenario}-{ts}.md"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump([summary], f, indent=2)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(render_markdown([summary], ts))

    print(f"\nScenario '{res.scenario}' completed.")
    print(f"Summary metrics: {summary['metrics']}")
    print(f"Artifacts: {md_file} & {json_file}")


if __name__ == "__main__":
    main()
