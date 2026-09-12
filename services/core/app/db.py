"""Lazy DB engine/session setup.

Nothing here connects to Postgres at import time. The engine is created on
first use (`get_engine()` / a request hitting `get_db()`), so the app can
still boot and serve `/health` with Postgres unreachable -- this matters for
a PHC deployment where Core must never be blocked by infra flakiness at
startup, and for running this service in a sandbox with no live database.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def db_reachable() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False
