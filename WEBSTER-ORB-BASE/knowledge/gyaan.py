"""Gyaan — source-aware local knowledge storage and retrieval (G4.5).

Only material explicitly supplied to Gyaan is stored. Search results retain their
source labels so callers can show where each retrieved item came from. This module
does not browse the web or treat stored text as executable instructions.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GyaanError(Exception):
    """Base exception for Gyaan storage and retrieval errors."""


class KnowledgeStore:
    """Thread-safe SQLite store for user-provided, source-labelled knowledge."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self.database_path = (
            Path(database_path) if database_path is not None
            else root / "data" / "gyaan.db"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _validate(value: str, field: str, limit: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text.")
        value = value.strip()
        if not value:
            raise ValueError(f"{field} cannot be empty.")
        if len(value) > limit:
            raise ValueError(f"{field} cannot exceed {limit} characters.")
        return value

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS knowledge (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL COLLATE NOCASE UNIQUE,
                        content TEXT NOT NULL,
                        source TEXT NOT NULL,
                        tags TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge(source)"
                )
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                logger.exception("Gyaan database initialization failed.")
                raise GyaanError("Could not initialize the Gyaan database.") from exc
            finally:
                connection.close()

    def add(
        self,
        title: str,
        content: str,
        source: str = "User-provided",
        tags: str = "",
    ) -> int:
        """Insert or update an item by title, preserving source attribution."""
        title = self._validate(title, "Title", 200)
        content = self._validate(content, "Content", 50000)
        source = self._validate(source, "Source", 500)
        if not isinstance(tags, str):
            raise ValueError("Tags must be text.")
        tags = tags.strip()
        if len(tags) > 500:
            raise ValueError("Tags cannot exceed 500 characters.")
        now = self._timestamp()
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    """INSERT INTO knowledge (title, content, source, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(title) DO UPDATE SET content=excluded.content,
                       source=excluded.source, tags=excluded.tags, updated_at=excluded.updated_at""",
                    (title, content, source, tags, now, now),
                )
                connection.commit()
                return int(cursor.lastrowid or 0)
            except sqlite3.Error as exc:
                connection.rollback()
                raise GyaanError("Could not save the knowledge item.") from exc
            finally:
                connection.close()

    def get(self, title: str) -> dict[str, Any] | None:
        title = self._validate(title, "Title", 200)
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM knowledge WHERE title = ? COLLATE NOCASE", (title,)
                ).fetchone()
                return dict(row) if row else None
            except sqlite3.Error as exc:
                raise GyaanError("Could not retrieve the knowledge item.") from exc
            finally:
                connection.close()

    @staticmethod
    def _terms(query: str) -> set[str]:
        return {term for term in re.findall(r"[\w'-]+", query.casefold()) if len(term) > 1}

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return deterministic keyword-ranked results with their source metadata."""
        query = self._validate(query, "Search query", 500)
        terms = self._terms(query)
        if not terms:
            return []
        limit = max(1, min(int(limit), 100))
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute("SELECT * FROM knowledge").fetchall()
                ranked = []
                for row in rows:
                    item = dict(row)
                    title = item["title"].casefold()
                    content = item["content"].casefold()
                    tags = item["tags"].casefold()
                    source = item["source"].casefold()
                    score = sum(
                        (4 if term in title else 0)
                        + (2 if term in tags else 0)
                        + content.count(term)
                        + (1 if term in source else 0)
                        for term in terms
                    )
                    if score:
                        item["score"] = score
                        ranked.append(item)
                ranked.sort(key=lambda item: (-item["score"], item["title"].casefold()))
                return ranked[:limit]
            except sqlite3.Error as exc:
                raise GyaanError("Could not search the knowledge base.") from exc
            finally:
                connection.close()

    def list_items(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM knowledge ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
                return [dict(row) for row in rows]
            except sqlite3.Error as exc:
                raise GyaanError("Could not list the knowledge base.") from exc
            finally:
                connection.close()

    def delete(self, title: str) -> bool:
        title = self._validate(title, "Title", 200)
        with self._lock:
            connection = self._connect()
            try:
                cursor = connection.execute(
                    "DELETE FROM knowledge WHERE title = ? COLLATE NOCASE", (title,)
                )
                connection.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as exc:
                connection.rollback()
                raise GyaanError("Could not delete the knowledge item.") from exc
            finally:
                connection.close()

    def count(self) -> int:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute("SELECT COUNT(*) AS total FROM knowledge").fetchone()
                return int(row["total"])
            finally:
                connection.close()

    def close(self) -> None:
        """Compatibility method; connections are closed after each operation."""
        return None


Gyaan = KnowledgeStore
