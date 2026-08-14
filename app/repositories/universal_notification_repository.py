"""Persistence for universal targeted notifications and consent/contact lifecycle."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class UniversalNotificationRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS universal_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER NOT NULL,
                    requester_user_id TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    wave INTEGER NOT NULL DEFAULT 1,
                    distance_km REAL,
                    relevance_score REAL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    provider_message_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(request_id, target_user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_universal_notifications_request
                    ON universal_notifications(request_id, status);
                CREATE INDEX IF NOT EXISTS idx_universal_notifications_target
                    ON universal_notifications(target_user_id, status);

                CREATE TABLE IF NOT EXISTS universal_interests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER NOT NULL,
                    requester_user_id TEXT NOT NULL,
                    responder_user_id TEXT NOT NULL,
                    responder_status TEXT NOT NULL DEFAULT 'INTERESTED',
                    requester_status TEXT NOT NULL DEFAULT 'PENDING',
                    contact_shared INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(request_id, responder_user_id)
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def reserve_notification(
        self,
        request_id: int,
        requester_user_id: str,
        target_user_id: str,
        wave: int = 1,
        distance_km: float | None = None,
        relevance_score: float | None = None,
    ) -> Optional[int]:
        now = self._now()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO universal_notifications (
                        request_id, requester_user_id, target_user_id, wave,
                        distance_km, relevance_score, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                    """,
                    (
                        int(request_id), str(requester_user_id), str(target_user_id),
                        int(wave), distance_km, relevance_score, now, now,
                    ),
                )
                return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return None

    def mark_sent(self, notification_id: int, provider_message_id: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_notifications
                SET status='SENT', provider_message_id=?, updated_at=?
                WHERE id=?
                """,
                (provider_message_id, self._now(), int(notification_id)),
            )

    def mark_failed(self, notification_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_notifications SET status='FAILED', updated_at=? WHERE id=?",
                (self._now(), int(notification_id)),
            )

    def contacted_user_ids(self, request_id: int) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT target_user_id FROM universal_notifications WHERE request_id=?",
                (int(request_id),),
            ).fetchall()
        return [str(row["target_user_id"]) for row in rows]

    def record_interest(self, request_id: int, requester_user_id: str, responder_user_id: str) -> int:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO universal_interests (
                    request_id, requester_user_id, responder_user_id,
                    responder_status, requester_status, contact_shared,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'INTERESTED', 'PENDING', 0, ?, ?)
                ON CONFLICT(request_id, responder_user_id) DO UPDATE SET
                    responder_status='INTERESTED', updated_at=excluded.updated_at
                """,
                (int(request_id), str(requester_user_id), str(responder_user_id), now, now),
            )
            row = conn.execute(
                "SELECT id FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (int(request_id), str(responder_user_id)),
            ).fetchone()
            return int(row["id"])

    def set_requester_consent(self, request_id: int, responder_user_id: str, accepted: bool) -> None:
        status = "ACCEPTED" if accepted else "REJECTED"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests SET requester_status=?, updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (status, self._now(), int(request_id), str(responder_user_id)),
            )

    def mark_contact_shared(self, request_id: int, responder_user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests SET contact_shared=1, updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (self._now(), int(request_id), str(responder_user_id)),
            )

    def get_interest(self, request_id: int, responder_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (int(request_id), str(responder_user_id)),
            ).fetchone()
        return dict(row) if row else None
