from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.rate_limiter import limiter
from app.db import session as db_session_module
from app.db.session import get_db

try:
    from main import app
except ImportError:
    from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("CRITICAL: TEST_DATABASE_URL is not set in environment!")

if "/hassan_ai_db" in TEST_DATABASE_URL:
    raise RuntimeError("CRITICAL: TEST_DATABASE_URL cannot point to primary development database!")

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"options": "-c client_encoding=utf8"},
    pool_pre_ping=True,
    poolclass=NullPool,
)

TestingSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

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


def _clean_database():
    """Dynamically truncate all application tables without touching schema or alembic_version."""
    with test_engine.begin() as conn:
        tables = conn.execute(
            text(
                """
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public' 
                  AND tablename NOT IN ('alembic_version', 'spatial_ref_sys');
                """
            )
        ).fetchall()
        if tables:
            names = ", ".join(f'"{t[0]}"' for t in tables)
            conn.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE;"))


@pytest.fixture(scope="session", autouse=True)
def prepare_database():
    _clean_database()
    yield
    _clean_database()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        _clean_database()


@pytest.fixture(autouse=True)
def reset_rate_limits():
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
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
