import time
from typing import Dict, Any
import httpx
from .metrics import ScenarioResult


async def benchmark_health_live(
    client: httpx.AsyncClient,
    result: ScenarioResult,
) -> None:
    t0 = time.perf_counter()
    try:
        response = await client.get("/health/live")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if response.status_code == 200:
            result.latencies_ms.append(elapsed_ms)
        else:
            result.errors += 1
    except Exception:
        result.errors += 1
