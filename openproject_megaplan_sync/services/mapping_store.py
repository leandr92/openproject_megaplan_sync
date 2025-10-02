"""Хранилище соответствий идентификаторов."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class MappingStore:
    """Обёртка над SQLite для хранения соответствий Megaplan ↔ OpenProject."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    # region schema
    def _init_schema(self) -> None:
        with closing(self._conn.cursor()) as cursor:
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    megaplan_id TEXT PRIMARY KEY,
                    openproject_id INTEGER NOT NULL,
                    synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS users (
                    megaplan_id TEXT PRIMARY KEY,
                    openproject_id INTEGER NOT NULL,
                    synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    megaplan_id TEXT PRIMARY KEY,
                    openproject_id INTEGER NOT NULL,
                    synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS comments (
                    megaplan_key TEXT PRIMARY KEY,
                    openproject_id INTEGER NOT NULL,
                    synced_at TEXT
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    project_id TEXT PRIMARY KEY,
                    last_sync TEXT
                );
                """
            )
            self._conn.commit()

    # endregion

    # region helpers
    def _upsert(self, table: str, key: str, value: int) -> None:
        now = datetime.utcnow().strftime(ISO_FORMAT)
        column = 'megaplan_id' if table != 'comments' else 'megaplan_key'
        sql = (
            f"INSERT INTO {table} ({column}, openproject_id, synced_at) VALUES (?, ?, ?)\n"
            f"ON CONFLICT({column}) DO UPDATE SET openproject_id = excluded.openproject_id, synced_at = excluded.synced_at"
        )
        self._conn.execute(sql, (key, value, now))
        self._conn.commit()

    def _get(self, table: str, key: str) -> Optional[int]:
        column = "megaplan_id" if table != "comments" else "megaplan_key"
        row = self._conn.execute(
            f"SELECT openproject_id FROM {table} WHERE {column} = ?",
            (key,),
        ).fetchone()
        return row[0] if row else None

    # endregion

    # region tasks
    def get_task(self, megaplan_id: str) -> Optional[int]:
        return self._get("tasks", megaplan_id)

    def upsert_task(self, megaplan_id: str, openproject_id: int) -> None:
        self._upsert("tasks", megaplan_id, openproject_id)

    # endregion

    # region users
    def get_user(self, megaplan_id: str) -> Optional[int]:
        return self._get("users", megaplan_id)

    def upsert_user(self, megaplan_id: str, openproject_id: int) -> None:
        self._upsert("users", megaplan_id, openproject_id)

    # endregion

    # region attachments
    def get_attachment(self, megaplan_id: str) -> Optional[int]:
        return self._get("attachments", megaplan_id)

    def upsert_attachment(self, megaplan_id: str, openproject_id: int) -> None:
        self._upsert("attachments", megaplan_id, openproject_id)

    # endregion

    # region comments
    def get_comment(self, megaplan_key: str) -> Optional[int]:
        return self._get("comments", megaplan_key)

    def upsert_comment(self, megaplan_key: str, openproject_id: int) -> None:
        self._upsert("comments", megaplan_key, openproject_id)

    # endregion

    # region sync state
    def get_last_sync(self, project_id: str) -> Optional[datetime]:
        row = self._conn.execute(
            "SELECT last_sync FROM sync_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        return datetime.strptime(row[0], ISO_FORMAT)

    def set_last_sync(self, project_id: str, moment: datetime) -> None:
        self._conn.execute(
            "INSERT INTO sync_state (project_id, last_sync) VALUES (?, ?)\n"
            "ON CONFLICT(project_id) DO UPDATE SET last_sync = excluded.last_sync",
            (project_id, moment.strftime(ISO_FORMAT)),
        )
        self._conn.commit()

    # endregion


__all__ = ["MappingStore"]
