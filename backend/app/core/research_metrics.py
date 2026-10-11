from __future__ import annotations
import asyncio
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator
from prometheus_client import Counter, Histogram

ACTIONS = frozenset({"retrieval", "synthesis", "export"})
OUTCOMES = frozenset({"success", "failure", "cancelled", "timeout"})
RESEARCH_OPERATIONS = Counter("ai_research_operations_total", "Research operation counts", ["action", "outcome"])
RESEARCH_DURATION = Histogram(
    "ai_research_operation_duration_seconds",
    "Research operation duration in seconds",
    ["action", "outcome"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

def record_research_operation(*, action: str, outcome: str, duration_seconds: float) -> None:
    if action not in ACTIONS:
        raise ValueError("Unsupported research action")
    if outcome not in OUTCOMES:
        raise ValueError("Unsupported research outcome")
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")
    RESEARCH_OPERATIONS.labels(action=action, outcome=outcome).inc()
    RESEARCH_DURATION.labels(action=action, outcome=outcome).observe(duration_seconds)

@contextmanager
def observe_research_operation(action: str) -> Iterator[None]:
    if action not in ACTIONS:
        raise ValueError("Unsupported research action")
    started, outcome = time.monotonic(), "success"
    try:
        yield
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    except TimeoutError:
        outcome = "timeout"
        raise
    except Exception:
        outcome = "failure"
        raise
    finally:
        record_research_operation(action=action, outcome=outcome, duration_seconds=max(0.0, time.monotonic() - started))

def observe_research_async_operation(action: str) -> Callable:
    if action not in ACTIONS:
        raise ValueError("Unsupported research action")
    def decorate(func: Callable) -> Callable:
        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            started, outcome = time.monotonic(), "success"
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except TimeoutError:
                outcome = "timeout"
                raise
            except Exception:
                outcome = "failure"
                raise
            finally:
                record_research_operation(action=action, outcome=outcome, duration_seconds=max(0.0, time.monotonic() - started))
        return wrapped
    return decorate
