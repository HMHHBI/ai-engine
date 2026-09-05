from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.models import User, UserPlan
from app.db.session import session_scope


@pytest.fixture
def test_user():
    unique_id = uuid.uuid4().hex[:8]
    email = f"tester_{unique_id}@example.com"
    with session_scope() as db:
        user = User(
            name="Persona Tester",
            email=email,
            password="hashed_dummy_password",
            plan=UserPlan.FREE,
        )
        db.add(user)
        db.flush()
        user_id = user.id
    return {"id": user_id, "email": email}


@pytest.fixture
def other_user():
    unique_id = uuid.uuid4().hex[:8]
    email = f"other_{unique_id}@example.com"
    with session_scope() as db:
        user = User(
            name="Other User",
            email=email,
            password="hashed_dummy_password",
            plan=UserPlan.FREE,
        )
        db.add(user)
        db.flush()
        user_id = user.id
    return {"id": user_id, "email": email}


def auth_header(user: dict) -> dict[str, str]:
    token = create_access_token(user_id=user["id"])
    return {"Authorization": f"Bearer {token}"}


def test_create_chat_default_persona(client: TestClient, test_user: dict):
    response = client.post(
        "/chat/new",
        json={},
        headers=auth_header(test_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["persona"] == "default"
    assert data["custom_instructions"] is None


def test_create_chat_with_custom_persona_and_instructions(
    client: TestClient, test_user: dict
):
    response = client.post(
        "/chat/new",
        json={
            "persona": "academic",
            "custom_instructions": "Always include formal citations.",
        },
        headers=auth_header(test_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["persona"] == "academic"
    assert data["custom_instructions"] == "Always include formal citations."


def test_update_persona_and_instructions(client: TestClient, test_user: dict):
    new_chat = client.post(
        "/chat/new",
        json={"persona": "default"},
        headers=auth_header(test_user),
    ).json()
    chat_id = new_chat["id"]

    patch_res = client.patch(
        f"/chat/{chat_id}/persona",
        json={
            "persona": "developer",
            "custom_instructions": "Write clean Python 3.11 code.",
        },
        headers=auth_header(test_user),
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["persona"] == "developer"
    assert updated["custom_instructions"] == "Write clean Python 3.11 code."

    details = client.get(
        f"/chat/details/{chat_id}",
        headers=auth_header(test_user),
    ).json()
    assert details["persona"] == "developer"
    assert details["custom_instructions"] == "Write clean Python 3.11 code."


def test_cross_user_cannot_update_persona(
    client: TestClient, test_user: dict, other_user: dict
):
    chat = client.post(
        "/chat/new",
        json={"persona": "default"},
        headers=auth_header(test_user),
    ).json()
    chat_id = chat["id"]

    res = client.patch(
        f"/chat/{chat_id}/persona",
        json={"persona": "legal"},
        headers=auth_header(other_user),
    )
    assert res.status_code == 404
