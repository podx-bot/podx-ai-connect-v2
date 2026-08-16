"""Pending AI-extracted catering menu awaiting one-time provider confirmation."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class CateringMenuPendingRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS catering_menu_pending (
                       provider_user_id TEXT PRIMARY KEY,
                       media_ref TEXT,
                       source_type TEXT,
                       items_json TEXT NOT NULL,
                       created_at TEXT NOT NULL,
                       updated_at TEXT NOT NULL
                   )"""
            )

    def save(self, provider_user_id: str, items: List[Dict[str, Any]], media_ref: str | None = None, source_type: str = "image") -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO catering_menu_pending(provider_user_id,media_ref,source_type,items_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(provider_user_id) DO UPDATE SET
                     media_ref=excluded.media_ref,source_type=excluded.source_type,items_json=excluded.items_json,updated_at=excluded.updated_at""",
                (str(provider_user_id), str(media_ref or ""), str(source_type), json.dumps(items or [], ensure_ascii=False), now, now),
            )

    def get(self, provider_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM catering_menu_pending WHERE provider_user_id=?", (str(provider_user_id),)).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            parsed = json.loads(data.get("items_json") or "[]")
            data["items"] = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            data["items"] = []
        return data

    def clear(self, provider_user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM catering_menu_pending WHERE provider_user_id=?", (str(provider_user_id),))
