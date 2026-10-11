import asyncio
import pytest
from prometheus_client import generate_latest
from app.core.research_metrics import (
    ACTIONS,
    RESEARCH_OPERATIONS,
    RESEARCH_DURATION,
    record_research_operation,
    observe_research_operation,
    observe_research_async_operation,
)


@pytest.mark.parametrize("action", sorted(ACTIONS))
@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled", "timeout"])
def test_counter_and_histogram_record(action, outcome):
    c = RESEARCH_OPERATIONS.labels(action=action, outcome=outcome)
    before = c._value.get()
    record_research_operation(action=action, outcome=outcome, duration_seconds=0.125)
    assert c._value.get() == before + 1

    body = generate_latest().decode("utf-8")
    assert f'ai_research_operations_total{{action="{action}",outcome="{outcome}"}}' in body
    assert f'ai_research_operation_duration_seconds_count{{action="{action}",outcome="{outcome}"}}' in body


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action": "workspace-123", "outcome": "success", "duration_seconds": 0.1},
        {"action": "export", "outcome": "email@example.com", "duration_seconds": 0.1},
        {"action": "export", "outcome": "success", "duration_seconds": -1},
    ],
)
def test_rejects_unbounded_or_invalid_labels(kwargs):
    with pytest.raises(ValueError):
        record_research_operation(**kwargs)


def test_exposition_contains_only_fixed_label_values():
    record_research_operation(action="retrieval", outcome="success", duration_seconds=0.01)
    body = generate_latest().decode("utf-8")
    assert 'action="retrieval"' in body and 'outcome="success"' in body
    for forbidden in ("query=", "prompt=", "filename=", "workspace_id=", "document_id=", "run_id="):
        assert forbidden not in body


def test_sync_context_manager_records_success_and_failure():
    before = RESEARCH_OPERATIONS.labels(action="export", outcome="success")._value.get()
    with observe_research_operation("export"):
        pass
    assert RESEARCH_OPERATIONS.labels(action="export", outcome="success")._value.get() == before + 1
    before = RESEARCH_OPERATIONS.labels(action="export", outcome="failure")._value.get()
    with pytest.raises(RuntimeError):
        with observe_research_operation("export"):
            raise RuntimeError("sensitive prompt")
    assert RESEARCH_OPERATIONS.labels(action="export", outcome="failure")._value.get() == before + 1


@pytest.mark.asyncio
async def test_async_decorator_records_success_and_failure():
    @observe_research_async_operation("retrieval")
    async def good():
        await asyncio.sleep(0)
        return 42

    before = RESEARCH_OPERATIONS.labels(action="retrieval", outcome="success")._value.get()
    assert await good() == 42
    assert RESEARCH_OPERATIONS.labels(action="retrieval", outcome="success")._value.get() == before + 1

    @observe_research_async_operation("synthesis")
    async def bad():
        raise RuntimeError("sensitive query")

    before = RESEARCH_OPERATIONS.labels(action="synthesis", outcome="failure")._value.get()
    with pytest.raises(RuntimeError):
        await bad()
    assert RESEARCH_OPERATIONS.labels(action="synthesis", outcome="failure")._value.get() == before + 1
