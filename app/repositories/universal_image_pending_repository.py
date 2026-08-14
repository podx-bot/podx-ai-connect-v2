"""Small persistent cache for image requests that need one intent clarification."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class UniversalImagePendingRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS universal_image_pending (
                    user_id TEXT PRIMARY KEY,
                    media_ref TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, user_id: str, media_ref: str, request: Dict[str, Any]) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO universal_image_pending(user_id, media_ref, request_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    media_ref=excluded.media_ref,
                    request_json=excluded.request_json,
                    updated_at=excluded.updated_at
                """,
                (str(user_id), str(media_ref), json.dumps(request, ensure_ascii=False), now, now),
            )

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_image_pending WHERE user_id=?",
                (str(user_id),),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["request"] = json.loads(data.pop("request_json") or "{}")
        return data

    def clear(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM universal_image_pending WHERE user_id=?", (str(user_id),))
