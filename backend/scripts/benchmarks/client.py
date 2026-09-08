from typing import Optional
import httpx


def create_benchmark_client(
    base_url: str,
    transport_mode: str = "http",
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    if transport_mode == "asgi":
        from app.main import app

        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=base_url,
            timeout=timeout,
        )
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
    )
