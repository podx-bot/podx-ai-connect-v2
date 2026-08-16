"""Persistent opt-in/out state for optional PODX discovery alerts."""
from __future__ import annotations

import sqlite3


class ProactiveAlertPreferenceRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS proactive_alert_preferences (
                    user_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def is_enabled(self, user_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT enabled FROM proactive_alert_preferences WHERE user_id=? LIMIT 1",
                (str(user_id),),
            ).fetchone()
        return True if row is None else bool(int(row["enabled"] or 0))

    def set_enabled(self, user_id: str, enabled: bool) -> bool:
        value = 1 if enabled else 0
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO proactive_alert_preferences(user_id, enabled, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (str(user_id), value),
            )
        return bool(value)

    def get(self, user_id: str) -> dict:
        return {"user_id": str(user_id), "enabled": self.is_enabled(user_id)}
