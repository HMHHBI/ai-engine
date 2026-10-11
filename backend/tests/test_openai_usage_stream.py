import pytest
from app.services.providers.openai_provider import OpenAIProvider


class FakeResponse:
    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
        yield (
            'data: {"choices":[],"usage":'
            '{"prompt_tokens":11,"completion_tokens":4,"total_tokens":15}}'
        )
        yield "data: [DONE]"


class FakeStreamContext:
    async def __aenter__(self):
        return FakeResponse()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return FakeStreamContext()


@pytest.mark.asyncio
async def test_openai_usage_only_chunk_is_captured_without_breaking_text_stream(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.providers.openai_provider.httpx.AsyncClient",
        FakeClient,
    )
    provider = OpenAIProvider()
    tokens = [
        token
        async for token in provider.generate_stream(
            prompt="test prompt",
        )
    ]
    assert tokens == ["hello"]
    assert provider.last_usage == {
        "input_tokens": 11,
        "output_tokens": 4,
        "total_tokens": 15,
    }
