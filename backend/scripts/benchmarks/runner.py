import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .client import create_benchmark_client
from .config import BenchmarkConfig
from .metrics import ScenarioResult
from .scenarios import benchmark_health_live
from .system_metrics import ProcessSampler


def render_markdown(results: list, timestamp: str) -> str:
    md = [
        f"# Performance Baseline Report — {timestamp}",
        "",
        "| Scenario | Concurrency | Iterations | Latency p50 (ms) | Latency p95 (ms) | Latency p99 (ms) | Errors |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for r in results:
        m = r["metrics"]["latency_ms"]
        md.append(
            f"| `{r['scenario']}` | {r['concurrency']} | {r['iterations']} | "
            f"{m['p50']} | {m['p95']} | {m['p99']} | {r['errors']} |"
        )
    md.append("")
    return "\n".join(md)


async def run_scenario(scenario_name: str, config: BenchmarkConfig) -> ScenarioResult:
    result = ScenarioResult(
        scenario=scenario_name,
        iterations=config.iterations,
        concurrency=config.concurrency,
        transport=config.transport,
    )
    sampler = ProcessSampler()

    async with create_benchmark_client(config.base_url, config.transport) as client:
        sem = asyncio.Semaphore(config.concurrency)

        async def worker():
            async with sem:
                if scenario_name == "health_live":
                    await benchmark_health_live(client, result)
                cpu, rss = sampler.sample()
                result.cpu_percent.append(cpu)
                result.rss_mb.append(rss)

        tasks = [asyncio.create_task(worker()) for _ in range(config.iterations)]
        await asyncio.gather(*tasks)

    return result


def main():
    parser = argparse.ArgumentParser(description="AI Engine Benchmark Harness")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL of backend"
    )
    parser.add_argument(
        "--iterations", type=int, default=20, help="Total benchmark iterations"
    )
    parser.add_argument(
        "--concurrency", type=int, default=1, help="Concurrent requests"
    )
    parser.add_argument(
        "--transport",
        choices=["http", "asgi"],
        default="http",
        help="Runner transport mode",
    )
    parser.add_argument(
        "--scenario",
        default="health_live",
        choices=["health_live"],
        help="Scenario to execute",
    )
    parser.add_argument(
        "--out-dir", default="benchmark-results", help="Directory for report output"
    )
    args = parser.parse_args()

    config = BenchmarkConfig(
        base_url=args.url,
        iterations=args.iterations,
        concurrency=args.concurrency,
        transport=args.transport,
        output_dir=args.out_dir,
    )

    print(
        f"Starting benchmark: {args.scenario} [{config.transport.upper()}] -> {config.base_url}"
    )
    print(f"Iterations: {config.iterations} | Concurrency: {config.concurrency}")

    res = asyncio.run(run_scenario(args.scenario, config))
    summary = res.summary()

    # Save artifacts
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(config.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / f"p2-01-baseline-{ts}.json"
    md_file = out_path / f"p2-01-baseline-{ts}.md"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump([summary], f, indent=2)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write(render_markdown([summary], ts))

    print(f"\nCompleted: {summary['metrics']['latency_ms']}")
    print(f"Artifacts generated:")
    print(f"  - {json_file}")
    print(f"  - {md_file}")


if __name__ == "__main__":
    main()
