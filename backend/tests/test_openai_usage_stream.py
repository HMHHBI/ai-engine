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


class MultiStreamClient:
    def __init__(self, **kwargs):
        self.call_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        self.call_count += 1
        is_first = (self.call_count == 1)

        class ParametricResponse:
            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"chunk"}}]}'
                if is_first:
                    yield 'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}'
                yield "data: [DONE]"

        class ParametricContext:
            async def __aenter__(self):
                return ParametricResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return ParametricContext()


@pytest.mark.asyncio
async def test_openai_reused_provider_instance_resets_last_usage(monkeypatch):
    client = MultiStreamClient()
    monkeypatch.setattr(
        "app.services.providers.openai_provider.httpx.AsyncClient",
        lambda **kwargs: client,
    )
    provider = OpenAIProvider()
    assert provider.last_usage is None

    # First stream: reports usage
    tokens_1 = [t async for t in provider.generate_stream(prompt="run 1")]
    assert tokens_1 == ["chunk"]
    assert provider.last_usage == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }

    # Second stream: does NOT report usage
    tokens_2 = [t async for t in provider.generate_stream(prompt="run 2")]
    assert tokens_2 == ["chunk"]
    assert provider.last_usage is None
