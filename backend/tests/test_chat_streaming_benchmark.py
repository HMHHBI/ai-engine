import pytest
from scripts.benchmarks.chat_streaming_benchmark import (
    StreamCollector,
    generate_synthetic_unit_vector,
)


def test_generate_synthetic_unit_vector():
    vec = generate_synthetic_unit_vector(768)
    assert len(vec) == 768
    norm = sum(x * x for x in vec) ** 0.5
    assert 0.99 <= norm <= 1.01


def test_stream_collector_lifecycle_parsing():
    collector = StreamCollector()
    lines = [
        "event: stream_started",
        'data: {"provider": "ollama", "model": "llama3.2"}',
        "",
        "event: sources",
        'data: {"sources": [{"id": 10}]}',
        "",
        "event: chunk",
        'data: {"text": "Hello "}',
        "",
        "event: chunk",
        'data: {"text": "world!"}',
        "",
        "event: stream_completed",
        'data: {"message_id": 100}',
    ]

    curr_event = None
    for line in lines:
        curr_event, is_completed = collector.parse_sse_line(line, curr_event)
        if is_completed:
            break

    assert collector.has_stream_started is True
    assert collector.chunks_count == 2
    assert collector.chars_count == len("Hello world!")
    assert collector.terminal_events == ["stream_completed"]
    assert len(collector.terminal_events) == 1
