
"""
WEBSTER — Smriti Memory System
G4.2

Responsibilities:
- Persistent SQLite memory.
- Explicitly save and retrieve user-approved memories.
- Search, update, list, and delete memories.
- Thread-safe database operations.

This module does not automatically collect personal information.
The caller must explicitly request a memory to be saved.
"""

from __future__ import annotations

import logging
import sqlite3
import threading

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class SmritiError(Exception):
    """Base exception for Smriti memory errors."""


class SmritiMemory:
    """Persistent, thread-safe memory manager."""

    def __init__(
        self,
        database_path: str | Path | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[1]

        self.database_path = (
            Path(database_path)
            if database_path is not None
            else project_root / "data" / "smriti.db"
        )

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._lock = threading.RLock()
        self._initialize_database()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.database_path),
            timeout=10.0,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        """Create the memory table if it does not exist."""

        with self._lock:
            connection = self._connect()

            try:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        memory_key TEXT NOT NULL UNIQUE,
                        memory_value TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'general',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)

                connection.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_memories_category
                    ON memories(category)
                """)

                connection.commit()

            except sqlite3.Error as exc:
                connection.rollback()
                logger.exception("Smriti database initialization failed.")
                raise SmritiError(
                    "Could not initialize the memory database."
                ) from exc

            finally:
                connection.close()

    @staticmethod
    def _validate_text(
        value: str,
        field: str,
        max_length: int = 10000,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string.")

        value = value.strip()

        if not value:
            raise ValueError(f"{field} cannot be empty.")

        if len(value) > max_length:
            raise ValueError(
                f"{field} cannot exceed {max_length} characters."
            )

        return value

    def save(
        self,
        key: str,
        value: str,
        category: str = "general",
    ) -> int:
        """
        Save a memory or update an existing memory with the same key.

        Call this only when the user explicitly asks WEBSTER to remember
        the supplied information.
        """

        key = self._validate_text(key, "Memory key", 200)
        value = self._validate_text(value, "Memory value")
        category = self._validate_text(
            category,
            "Category",
            100,
        )

        now = self._timestamp()

        with self._lock:
            connection = self._connect()

            try:
                cursor = connection.execute(
                    """
                    INSERT INTO memories (
                        memory_key,
                        memory_value,
                        category,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(memory_key)
                    DO UPDATE SET
                        memory_value = excluded.memory_value,
                        category = excluded.category,
                        updated_at = excluded.updated_at
                    """,
                    (key, value, category, now, now),
                )

                connection.commit()
                return cursor.lastrowid or 0

            except sqlite3.Error as exc:
                connection.rollback()
                logger.exception("Smriti could not save a memory.")
                raise SmritiError(
                    "Could not save the memory."
                ) from exc

            finally:
                connection.close()

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve one memory by its exact key."""

        key = self._validate_text(key, "Memory key", 200)

        with self._lock:
            connection = self._connect()

            try:
                row = connection.execute(
                    """
                    SELECT *
                    FROM memories
                    WHERE memory_key = ?
                    """,
                    (key,),
                ).fetchone()

                return dict(row) if row else None

            except sqlite3.Error as exc:
                raise SmritiError(
                    "Could not retrieve the memory."
                ) from exc

            finally:
                connection.close()

    def search(
        self,
        query: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search memory keys, values, and categories."""

        query = self._validate_text(query, "Search query", 200)
        limit = max(1, min(int(limit), 100))

        pattern = f"%{query}%"

        with self._lock:
            connection = self._connect()

            try:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM memories
                    WHERE memory_key LIKE ?
                       OR memory_value LIKE ?
                       OR category LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit),
                ).fetchall()

                return [dict(row) for row in rows]

            except sqlite3.Error as exc:
                raise SmritiError(
                    "Could not search memories."
                ) from exc

            finally:
                connection.close()

    def list_memories(
        self,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List saved memories, optionally filtered by category."""

        limit = max(1, min(int(limit), 500))

        with self._lock:
            connection = self._connect()

            try:
                if category is None:
                    rows = connection.execute(
                        """
                        SELECT *
                        FROM memories
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
                else:
                    category = self._validate_text(
                        category,
                        "Category",
                        100,
                    )

                    rows = connection.execute(
                        """
                        SELECT *
                        FROM memories
                        WHERE category = ?
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (category, limit),
                    ).fetchall()

                return [dict(row) for row in rows]

            except sqlite3.Error as exc:
                raise SmritiError(
                    "Could not list memories."
                ) from exc

            finally:
                connection.close()

    def delete(self, key: str) -> bool:
        """Delete one memory by its exact key."""

        key = self._validate_text(key, "Memory key", 200)

        with self._lock:
            connection = self._connect()

            try:
                cursor = connection.execute(
                    "DELETE FROM memories WHERE memory_key = ?",
                    (key,),
                )

                connection.commit()
                return cursor.rowcount > 0

            except sqlite3.Error as exc:
                connection.rollback()
                raise SmritiError(
                    "Could not delete the memory."
                ) from exc

            finally:
                connection.close()

    def clear(self, category: str | None = None) -> int:
        """
        Delete all memories, or all memories in one category.

        Returns the number of deleted records.
        """

        with self._lock:
            connection = self._connect()

            try:
                if category is None:
                    cursor = connection.execute(
                        "DELETE FROM memories"
                    )
                else:
                    category = self._validate_text(
                        category,
                        "Category",
                        100,
                    )

                    cursor = connection.execute(
                        "DELETE FROM memories WHERE category = ?",
                        (category,),
                    )

                connection.commit()
                return cursor.rowcount

            except sqlite3.Error as exc:
                connection.rollback()
                raise SmritiError(
                    "Could not clear memories."
                ) from exc

            finally:
                connection.close()

    def count(self) -> int:
        """Return the number of stored memories."""

        with self._lock:
            connection = self._connect()

            try:
                row = connection.execute(
                    "SELECT COUNT(*) AS total FROM memories"
                ).fetchone()

                return int(row["total"])

            finally:
                connection.close()

    def close(self) -> None:
        """Compatibility method; connections are closed per operation."""
        return None


# Short alias for convenient imports.
Smriti = SmritiMemory
