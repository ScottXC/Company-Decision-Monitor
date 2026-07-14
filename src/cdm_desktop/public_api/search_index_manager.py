from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


class SearchIndexManager:
    """Process-level owner for immutable search indexes and thread-local connections."""

    _instances: dict[Path, SearchIndexManager] = {}
    _instances_lock = threading.Lock()

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._local = threading.local()
        self._schema_lock = threading.Lock()
        self._schema_checked = False
        self._objects: frozenset[str] = frozenset()
        self._metadata: dict[str, Any] | None = None
        self.connection_count = 0

    @classmethod
    def for_path(cls, path: Path) -> SearchIndexManager:
        resolved = path.resolve()
        with cls._instances_lock:
            manager = cls._instances.get(resolved)
            if manager is None:
                manager = cls(resolved)
                cls._instances[resolved] = manager
            return manager

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._instances_lock:
            managers = list(cls._instances.values())
            cls._instances.clear()
        for manager in managers:
            manager.close_current_thread()

    def connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            uri = f"{self.path.as_uri()}?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True, timeout=1.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            self._local.connection = connection
            self.connection_count += 1
        self._ensure_schema(connection)
        return connection

    def has_object(self, name: str) -> bool:
        self.connection()
        return name in self._objects

    def metadata(self) -> dict[str, Any]:
        if self._metadata is not None:
            return dict(self._metadata)
        connection = self.connection()
        metadata: dict[str, Any] = {}
        if "metadata" in self._objects:
            for key, value in connection.execute("SELECT key, value FROM metadata"):
                metadata[str(key)] = value
        self._metadata = metadata
        return dict(metadata)

    def warmup(self) -> None:
        connection = self.connection()
        connection.execute("SELECT 1 FROM symbols LIMIT 1").fetchone()

    def close_current_thread(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            del self._local.connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        if self._schema_checked:
            return
        with self._schema_lock:
            if self._schema_checked:
                return
            self._objects = frozenset(
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            )
            if not {"symbols", "aliases"}.issubset(self._objects):
                raise sqlite3.DatabaseError("search index schema is incomplete")
            self._schema_checked = True
