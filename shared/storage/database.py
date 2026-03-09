import sqlite3
from contextlib import contextmanager
from pathlib import Path

from shared.config.settings import settings


def get_db_path() -> Path:
    path = settings.sqlite_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_connection():
    """Yield a sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
