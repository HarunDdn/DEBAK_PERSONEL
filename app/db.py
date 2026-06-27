"""Veritabani baglanti yardimcilari (pyodbc)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .config import get_settings


@contextmanager
def get_connection() -> Iterator["pyodbc.Connection"]:  # type: ignore[name-defined]
    """CANIAS MSSQL veritabanina pyodbc baglantisi acar ve kapatir."""
    import pyodbc  # lazy import: test ortaminda surucu gerekmesin

    settings = get_settings()
    conn = pyodbc.connect(settings.odbc_connection_string())
    try:
        yield conn
    finally:
        conn.close()
