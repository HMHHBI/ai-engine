import math
from dataclasses import dataclass, field
from typing import Any, Dict, List


def calculate_percentile(data: List[float], percentile: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_data[int(k)])
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return float(d0 + d1)


@dataclass
class ScenarioResult:
    scenario: str
    iterations: int
    concurrency: int
    transport: str
    latencies_ms: List[float] = field(default_factory=list)
    ttft_ms: List[float] = field(default_factory=list)
    stream_duration_ms: List[float] = field(default_factory=list)
    chunk_counts: List[int] = field(default_factory=list)
    character_counts: List[int] = field(default_factory=list)
    errors: int = 0
    cancellations: int = 0
    cpu_percent: List[float] = field(default_factory=list)
    rss_mb: List[float] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        has_streams = bool(self.stream_duration_ms)
        total_chunks = sum(self.chunk_counts)
        total_chars = sum(self.character_counts)
        total_stream_sec = (
            sum(self.stream_duration_ms) / 1000.0 if self.stream_duration_ms else 0.0
        )

        return {
            "scenario": self.scenario,
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "transport": self.transport,
            "errors": self.errors,
            "cancellations": self.cancellations,
            "metrics": {
                "latency_ms": {
                    "p50": round(calculate_percentile(self.latencies_ms, 50), 2),
                    "p95": round(calculate_percentile(self.latencies_ms, 95), 2),
                    "p99": round(calculate_percentile(self.latencies_ms, 99), 2),
                    "min": (
                        round(min(self.latencies_ms), 2) if self.latencies_ms else 0.0
                    ),
                    "max": (
                        round(max(self.latencies_ms), 2) if self.latencies_ms else 0.0
                    ),
                },
                "ttft_ms": (
                    {
                        "p50": round(calculate_percentile(self.ttft_ms, 50), 2),
                        "p95": round(calculate_percentile(self.ttft_ms, 95), 2),
                        "p99": round(calculate_percentile(self.ttft_ms, 99), 2),
                    }
                    if self.ttft_ms
                    else None
                ),
                "stream_duration_ms": (
                    {
                        "p50": round(
                            calculate_percentile(self.stream_duration_ms, 50), 2
                        ),
                        "p95": round(
                            calculate_percentile(self.stream_duration_ms, 95), 2
                        ),
                        "p99": round(
                            calculate_percentile(self.stream_duration_ms, 99), 2
                        ),
                    }
                    if has_streams
                    else None
                ),
                "streaming_rates": (
                    {
                        "chunks_per_sec": (
                            round(total_chunks / total_stream_sec, 2)
                            if total_stream_sec > 0
                            else 0.0
                        ),
                        "characters_per_sec": (
                            round(total_chars / total_stream_sec, 2)
                            if total_stream_sec > 0
                            else 0.0
                        ),
                        "avg_chunks_per_response": (
                            round(total_chunks / len(self.chunk_counts), 2)
                            if self.chunk_counts
                            else 0.0
                        ),
                    }
                    if has_streams
                    else None
                ),
                "system": {
                    "cpu_percent_avg": (
                        round(sum(self.cpu_percent) / len(self.cpu_percent), 2)
                        if self.cpu_percent
                        else 0.0
                    ),
                    "rss_mb_peak": round(max(self.rss_mb), 2) if self.rss_mb else 0.0,
                },
            },
        }
