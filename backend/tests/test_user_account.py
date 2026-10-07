from __future__ import annotations

import time
from app.core.security import create_access_token
from app.db.models import UserPlan
from app.repositories.user_repo import UserRepository


def auth_headers(user) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )
    return {
        "Authorization": f"Bearer {token}",
    }


def create_user(db_session, suffix: str):
    return UserRepository.create(
        db_session,
        name=f"User {suffix}",
        email=f"user-{suffix}-{int(time.time() * 1000000)}@example.com",
        password="Password!123",
    )


def test_user_me_returns_account_reality(client, db_session):
    user = create_user(db_session, "profile")
    user.plan = UserPlan.STANDARD
    user.image_limit = 7
    user.search_limit = 19
    db_session.commit()

    response = client.get("/user/me", headers=auth_headers(user))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user.id
    assert data["full_name"] == user.name
    assert data["email"] == user.email
    assert data["plan"] == "STANDARD"
    assert data["limits"]["image"] == 7
    assert data["limits"]["search"] == 19


def test_user_usage_returns_remaining_quotas(client, db_session):
    user = create_user(db_session, "usage")
    user.plan = UserPlan.PRO
    user.image_limit = 50
    user.search_limit = 100
    db_session.commit()

    response = client.get("/user/usage", headers=auth_headers(user))
    assert response.status_code == 200
    data = response.json()
    assert data["plan"] == "PRO"
    assert data["image"]["remaining"] == 50
    assert data["search"]["remaining"] == 100


def test_user_usage_requires_authentication(client):
    response = client.get("/user/usage")
    assert response.status_code == 401


def test_user_usage_isolates_tenants(client, db_session):
    user_a = create_user(db_session, "tenant_a")
    user_a.image_limit = 5
    user_a.search_limit = 10

    user_b = create_user(db_session, "tenant_b")
    user_b.image_limit = 20
    user_b.search_limit = 40
    db_session.commit()

    res_a = client.get("/user/usage", headers=auth_headers(user_a))
    assert res_a.status_code == 200
    assert res_a.json()["image"]["remaining"] == 5

    res_b = client.get("/user/usage", headers=auth_headers(user_b))
    assert res_b.status_code == 200
    assert res_b.json()["image"]["remaining"] == 20


def test_user_usage_clamps_negative_counters(client, db_session):
    user = create_user(db_session, "negative")
    user.image_limit = -3
    user.search_limit = -10
    db_session.commit()

    response = client.get("/user/usage", headers=auth_headers(user))
    assert response.status_code == 200
    data = response.json()
    assert data["image"]["remaining"] == 0
    assert data["search"]["remaining"] == 0
