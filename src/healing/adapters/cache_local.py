"""Local SQLite cache adapter."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .base import CacheAdapter


class LocalSQLiteCache(CacheAdapter):
    """SQLite-backed cache for local environments."""

    def __init__(self, path: Optional[Path] = None):
        """Initialize SQLite cache.

        Args:
            path: Path to SQLite database file. Defaults to .claude/healing_cache.sqlite.
        """
        if path is None:
            path = Path.cwd() / ".claude" / "healing_cache.sqlite"
        self.path = Path(path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode for better concurrency."""
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    async def get(self, key: str) -> Optional[dict]:
        """Get cached value from SQLite."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            value, expires_at = row
            if time.time() > expires_at:
                # Expired, delete it
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                return None

            return json.loads(value)
        finally:
            conn.close()

    async def set(self, key: str, value: dict, ttl_seconds: int = 3600) -> None:
        """Set cached value in SQLite."""
        expires_at = time.time() + ttl_seconds
        value_json = json.dumps(value)

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, value_json, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    async def delete(self, key: str) -> None:
        """Delete cached value from SQLite."""
        conn = self._get_connection()
        try:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    async def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of deleted entries."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM cache WHERE expires_at < ?",
                (time.time(),),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
