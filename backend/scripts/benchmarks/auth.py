import os
from typing import Dict
import httpx

BENCHMARK_EMAIL = os.getenv("BENCHMARK_EMAIL", "perf_test_runner@benchmark.internal")
BENCHMARK_PASSWORD = os.getenv("BENCHMARK_PASSWORD", "PerfRunnerSecret#2026")
BENCHMARK_NAME = os.getenv("BENCHMARK_NAME", "Benchmark Runner")


async def get_authenticated_headers(
    client: httpx.AsyncClient,
    email: str = BENCHMARK_EMAIL,
    password: str = BENCHMARK_PASSWORD,
    name: str = BENCHMARK_NAME,
) -> Dict[str, str]:
    login_payload = {"email": email, "password": password}

    # 1. Attempt login first
    login_resp = await client.post("/auth/login", json=login_payload)
    if login_resp.status_code == 200:
        token = login_resp.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}

    # 2. If absent, register user
    signup_payload = {
        "email": email,
        "name": name,
        "password": password,
    }
    await client.post("/auth/signup", json=signup_payload)

    # 3. Complete login to retrieve JWT
    login_resp = await client.post("/auth/login", json=login_payload)
    if login_resp.status_code == 200:
        token = login_resp.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}

    raise RuntimeError(
        f"Benchmark auth bootstrap failed: status {login_resp.status_code}, body: {login_resp.text}"
    )
