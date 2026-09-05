from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.rate_limiter import limiter
from app.db import session as db_session_module
from app.db.models import Base
from app.db.session import get_db

try:
    from main import app
except ImportError:
    from app.main import app

# 1. Directly read isolated test database URL from environment
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "CRITICAL: TEST_DATABASE_URL is not set in environment! "
        "Define TEST_DATABASE_URL in .env or docker-compose to prevent tests from hitting dev DB."
    )

if "/hassan_ai_db" in TEST_DATABASE_URL:
    raise RuntimeError(
        "CRITICAL: TEST_DATABASE_URL cannot point to primary development database (hassan_ai_db)!"
    )

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={
        "options": "-c client_encoding=utf8",
    },
    pool_pre_ping=True,
    poolclass=NullPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# 2. Redirect app internals to test engine
db_session_module.engine = test_engine
db_session_module.SessionLocal = TestingSessionLocal


@contextmanager
def _test_session_scope() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


db_session_module.session_scope = _test_session_scope


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset slowapi rate limits before and after every test."""
    try:
        limiter.reset()
    except Exception:
        pass
    yield
    try:
        limiter.reset()
    except Exception:
        pass


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
