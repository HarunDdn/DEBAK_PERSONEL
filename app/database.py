from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.config import get_settings


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


@contextmanager
def get_connection() -> Generator[Connection, None, None]:
    with get_engine().connect() as connection:
        yield connection


def fetch_all(connection: Connection, query: str, params: dict | None = None) -> list[dict]:
    result = connection.execute(text(query), params or {})
    return [dict(row._mapping) for row in result]


def fetch_one(connection: Connection, query: str, params: dict | None = None) -> dict | None:
    rows = fetch_all(connection, query, params)
    return rows[0] if rows else None
