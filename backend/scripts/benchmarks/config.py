import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkConfig:
    base_url: str = os.getenv("BENCHMARK_BASE_URL", "http://localhost:8000")
    iterations: int = int(os.getenv("BENCHMARK_ITERATIONS", "20"))
    concurrency: int = int(os.getenv("BENCHMARK_CONCURRENCY", "1"))
    transport: str = os.getenv("BENCHMARK_TRANSPORT", "http")  # 'http' or 'asgi'
    output_dir: str = os.getenv("BENCHMARK_OUTPUT_DIR", "benchmark-results")
