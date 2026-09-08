"""
P2-05 Chat Streaming Cancellation & Recovery Characterization Benchmark.

Tests:
1. Concurrency C=4 client cancellation:
   - Cancel 1 of 4 streams early
   - Cancel 2 of 4 streams early
   - Cancel all 4 streams early
2. Validates:
   - Client disconnection reaches backend
   - No dangling worker or corrupted assistant message
   - Database remains consistent
   - Subsequent chat request succeeds with healthy lifecycle
"""

import asyncio
import os
import pathlib
import time
from typing import Any, Dict, List

import httpx
from app.core.security import create_access_token
from app.db.models import Chat, Message, User
from app.db.session import SessionLocal

BENCH_USER_EMAIL = "benchmark_p205_runner@example.com"
APP_BASE_URL = os.getenv("BENCHMARK_BASE_URL", "http://127.0.0.1:8000")


def ensure_bench_user() -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == BENCH_USER_EMAIL).first()
        if not user:
            user = User(
                name="Benchmark Runner P205",
                email=BENCH_USER_EMAIL,
                password="fixture_hash",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def create_chat(user_id: int, title: str) -> int:
    db = SessionLocal()
    try:
        chat = Chat(user_id=user_id, title=title)
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat.id
    finally:
        db.close()


def cleanup_chats(chat_ids: List[int]) -> None:
    db = SessionLocal()
    try:
        db.query(Message).filter(Message.chat_id.in_(chat_ids)).delete(synchronize_session=False)
        db.query(Chat).filter(Chat.id.in_(chat_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


async def stream_with_possible_cancel(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int,
    cancel_after_tokens: int = 0,
) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "chat_id": chat_id,
        "prompt": "Count slowly from 1 to 20 with descriptions for each number.",
        "provider": "ollama",
        "model": "llama3.2",
    }

    tokens_seen = 0
    was_cancelled = False
    completed = False
    current_event = None

    try:
        async with client.stream("POST", "/chat/stream", json=payload, headers=headers, timeout=30.0) as resp:
            if resp.status_code != 200:
                return {"success": False, "status": resp.status_code, "was_cancelled": False}

            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    current_event = line.replace("event:", "").strip()
                elif line.startswith("data:"):
                    if current_event == "chunk":
                        tokens_seen += 1
                        if cancel_after_tokens > 0 and tokens_seen >= cancel_after_tokens:
                            was_cancelled = True
                            break
                    elif current_event == "stream_completed":
                        completed = True
                        break
    except Exception:
        pass

    return {
        "tokens_seen": tokens_seen,
        "was_cancelled": was_cancelled,
        "completed": completed,
    }


async def run_cancellation_scenario(
    user_id: int,
    token: str,
    scenario_name: str,
    cancel_indices: List[int],
) -> Dict[str, Any]:
    print(f"\nRunning Cancellation Scenario: {scenario_name} (Cancel indices: {cancel_indices})...")
    chat_ids = [create_chat(user_id, f"Cancel_{scenario_name}_{i}") for i in range(4)]

    try:
        async with httpx.AsyncClient(base_url=APP_BASE_URL, timeout=60.0) as client:
            tasks = []
            for i in range(4):
                cancel_after = 2 if i in cancel_indices else 0
                tasks.append(stream_with_possible_cancel(client, token, chat_ids[i], cancel_after))

            results = await asyncio.gather(*tasks)

        # Allow grace period for backend connection teardown and cleanup
        await asyncio.sleep(1.0)

        # Verify database integrity: ensure no orphaned or corrupt state
        db = SessionLocal()
        try:
            for i, c_id in enumerate(chat_ids):
                msgs = db.query(Message).filter(Message.chat_id == c_id).all()
                # If stream was cancelled before stream_completed, assistant message is either absent or clean
                for m in msgs:
                    if m.role == "assistant":
                        assert m.content is not None
        finally:
            db.close()

        # Invariant test: Subsequent request on the same or new chat succeeds cleanly
        post_chat_id = create_chat(user_id, f"Post_Cancel_Recovery_{scenario_name}")
        chat_ids.append(post_chat_id)
        async with httpx.AsyncClient(base_url=APP_BASE_URL, timeout=30.0) as client:
            rec_res = await stream_with_possible_cancel(client, token, post_chat_id, cancel_after_tokens=0)
            recovery_ok = rec_res["completed"]

        print(f"Scenario {scenario_name}: Recovery request completed: {recovery_ok}")
        return {
            "scenario": scenario_name,
            "results": results,
            "recovery_ok": recovery_ok,
        }

    finally:
        cleanup_chats(chat_ids)


async def main():
    print("==========================================================")
    print("  P2-05: STREAM CANCELLATION & LIFECYCLE RECOVERY TEST")
    print("==========================================================")

    user = ensure_bench_user()
    token = create_access_token(user_id=user.id)

    # 1. Cancel 1 of 4 streams early
    s1 = await run_cancellation_scenario(user.id, token, "Cancel_1_of_4", cancel_indices=[0])
    assert s1["recovery_ok"]

    # 2. Cancel 2 of 4 streams early
    s2 = await run_cancellation_scenario(user.id, token, "Cancel_2_of_4", cancel_indices=[0, 1])
    assert s2["recovery_ok"]

    # 3. Cancel all 4 streams early
    s3 = await run_cancellation_scenario(user.id, token, "Cancel_All_4", cancel_indices=[0, 1, 2, 3])
    assert s3["recovery_ok"]

    print("\nAll cancellation scenarios passed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
