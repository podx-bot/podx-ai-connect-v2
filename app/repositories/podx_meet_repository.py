"""Persistent local PODX Meet events and attendance."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class PodxMeetRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS podx_meets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host_user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    scheduled_text TEXT NOT NULL,
                    area TEXT NOT NULL,
                    details TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS podx_meet_attendees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meet_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'JOINED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(meet_id, user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_podx_meets_area_status ON podx_meets(area,status,id);
                CREATE INDEX IF NOT EXISTS idx_podx_meet_attendees ON podx_meet_attendees(meet_id,status,id);
                """
            )

    def create(self, host_user_id: str, title: str, scheduled_text: str, area: str, details: str = "") -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO podx_meets(host_user_id,title,scheduled_text,area,details,status,created_at,updated_at) VALUES(?,?,?,?,?,'OPEN',?,?)",
                (str(host_user_id), title.strip(), scheduled_text.strip(), area.strip(), details.strip(), now, now),
            )
            return int(cur.lastrowid)

    def get(self, meet_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM podx_meets WHERE id=?", (int(meet_id),)).fetchone()
        return dict(row) if row else None

    def list_open(self, area: str | None = None, limit: int = 10) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM podx_meets WHERE status='OPEN'"
        params: list[Any] = []
        if area:
            sql += " AND lower(area) LIKE ?"
            params.append(f"%{str(area).casefold().strip()}%")
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def join(self, meet_id: int, user_id: str) -> bool:
        meet = self.get(meet_id)
        if not meet or str(meet.get("status")) != "OPEN":
            return False
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO podx_meet_attendees(meet_id,user_id,status,created_at,updated_at) VALUES(?,?,'JOINED',?,?) ON CONFLICT(meet_id,user_id) DO UPDATE SET status='JOINED',updated_at=excluded.updated_at",
                (int(meet_id), str(user_id), now, now),
            )
        return True

    def leave(self, meet_id: int, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE podx_meet_attendees SET status='LEFT',updated_at=? WHERE meet_id=? AND user_id=? AND status='JOINED'",
                (self._now(), int(meet_id), str(user_id)),
            )
            return int(cur.rowcount or 0) > 0

    def cancel(self, meet_id: int, host_user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE podx_meets SET status='CANCELLED',updated_at=? WHERE id=? AND host_user_id=? AND status='OPEN'",
                (self._now(), int(meet_id), str(host_user_id)),
            )
            return int(cur.rowcount or 0) > 0

    def attendee_count(self, meet_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM podx_meet_attendees WHERE meet_id=? AND status='JOINED'",
                (int(meet_id),),
            ).fetchone()
        return int(row["n"] if row else 0)

    def is_joined(self, meet_id: int, user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM podx_meet_attendees WHERE meet_id=? AND user_id=? AND status='JOINED' LIMIT 1",
                (int(meet_id), str(user_id)),
            ).fetchone()
        return row is not None
