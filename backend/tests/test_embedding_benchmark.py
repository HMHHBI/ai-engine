import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from scripts.benchmarks.embedding_benchmark import run_microbenchmark_sweep, run_batch_sweep

@pytest.mark.asyncio
async def test_microbenchmark_sweep_mocked():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embedding": [0.1] * 768}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        results = await run_microbenchmark_sweep(concurrency_levels=[1, 2], n_requests=4, warmup=1)

        assert len(results) == 2
        assert results[0]["concurrency"] == 1
        assert results[0]["successful"] == 4
        assert results[0]["errors"] == 0
        assert "throughput_emb_sec" in results[0]
        assert "p50_ms" in results[0]

@pytest.mark.asyncio
async def test_batch_sweep_mocked():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"embeddings": [[0.1] * 768]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        results = await run_batch_sweep(batch_sizes=[1, 4], total_items=4)

        assert len(results) == 2
        assert results[0]["batch_size"] == 1
        assert results[1]["batch_size"] == 4
        assert results[0]["errors"] == 0
