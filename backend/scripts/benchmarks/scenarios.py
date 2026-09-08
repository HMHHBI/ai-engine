import json
import time
from typing import Any, Dict, Optional
import httpx
from .metrics import ScenarioResult


async def benchmark_health_live(
    client: httpx.AsyncClient,
    result: ScenarioResult,
    headers: Optional[Dict[str, str]] = None,
) -> None:
    t0 = time.perf_counter()
    try:
        response = await client.get("/health/live", headers=headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if response.status_code == 200:
            result.latencies_ms.append(elapsed_ms)
        else:
            result.errors += 1
    except Exception:
        result.errors += 1


async def benchmark_chat_non_rag(
    client: httpx.AsyncClient,
    result: ScenarioResult,
    headers: Dict[str, str],
    chat_id: int,
    prompt: str = "Explain the difference between synchronous and asynchronous I/O in two concise paragraphs.",
) -> None:
    payload = {
        "chat_id": chat_id,
        "prompt": prompt,
        "task": "general",
        "document_id": None,
    }

    t0 = time.perf_counter()
    ttft_ms: Optional[float] = None
    chunks_count = 0
    chars_count = 0
    completed = False
    current_event: Optional[str] = None

    try:
        async with client.stream(
            "POST", "/chat/stream", json=payload, headers=headers, timeout=120.0
        ) as response:
            if response.status_code != 200:
                result.errors += 1
                return

            async for line in response.aiter_lines():
                if not line or line.startswith(":"):
                    continue

                if line.startswith("event:"):
                    current_event = line.replace("event:", "").strip()
                    continue

                if line.startswith("data:"):
                    raw_data = line.replace("data:", "").strip()
                    try:
                        data = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    # Server-side stream error handling
                    if current_event == "stream_error":
                        result.errors += 1
                        return

                    text = data.get("text", "")
                    if text and ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t0) * 1000.0

                    if text:
                        chunks_count += 1
                        chars_count += len(text)

                    if (
                        current_event == "stream_completed"
                        or data.get("event") == "stream_completed"
                        or data.get("done") is True
                    ):
                        completed = True

        total_duration_ms = (time.perf_counter() - t0) * 1000.0

        if ttft_ms is not None:
            result.ttft_ms.append(ttft_ms)
        result.latencies_ms.append(total_duration_ms)
        result.stream_duration_ms.append(total_duration_ms)
        result.chunk_counts.append(chunks_count)
        result.character_counts.append(chars_count)

        if not completed:
            result.cancellations += 1

    except httpx.RequestError:
        result.errors += 1
