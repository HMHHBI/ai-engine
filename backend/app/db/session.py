from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "options": "-c client_encoding=utf8",
    },
    pool_pre_ping=True,
)


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI request-scoped database dependency.

    This session belongs to the request thread and must not be passed
    into asyncio/threadpool/background execution.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Repository/background-worker database session.

    The caller owns no session. This context manager guarantees that
    every repository operation gets an isolated session and that the
    session is always closed.
    """

    db = SessionLocal()

    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
