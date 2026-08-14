"""Persistence for universal targeted notifications and lead-conversion lifecycle.

Lead-conversion role convention (independent of who created the original
NEED/OFFER record):
- universal_interests.requester_user_id stores the BUYER user id.
- universal_interests.responder_user_id stores the SELLER user id.
- requester_status is retained for backward-compatible schema reasons, but it
  represents the SELLER decision (PENDING/ACCEPTED/REJECTED).
"""

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
                    qualification_status TEXT NOT NULL DEFAULT 'NEW',
                    delivery_address TEXT,
                    converted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(request_id, responder_user_id)
                );
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(universal_interests)").fetchall()
            }
            if "qualification_status" not in columns:
                conn.execute(
                    "ALTER TABLE universal_interests ADD COLUMN qualification_status TEXT NOT NULL DEFAULT 'NEW'"
                )
            if "delivery_address" not in columns:
                conn.execute("ALTER TABLE universal_interests ADD COLUMN delivery_address TEXT")
            if "converted_at" not in columns:
                conn.execute("ALTER TABLE universal_interests ADD COLUMN converted_at TEXT")

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

    def record_interest(self, request_id: int, buyer_user_id: str, seller_user_id: str) -> int:
        """Persist a buyer selecting a seller for this matched request."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO universal_interests (
                    request_id, requester_user_id, responder_user_id,
                    responder_status, requester_status, contact_shared,
                    qualification_status, created_at, updated_at
                ) VALUES (?, ?, ?, 'INTERESTED', 'PENDING', 0, 'NEW', ?, ?)
                ON CONFLICT(request_id, responder_user_id) DO UPDATE SET
                    requester_user_id=excluded.requester_user_id,
                    responder_status='INTERESTED', requester_status='PENDING',
                    qualification_status='NEW', updated_at=excluded.updated_at
                """,
                (int(request_id), str(buyer_user_id), str(seller_user_id), now, now),
            )
            row = conn.execute(
                "SELECT id FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (int(request_id), str(seller_user_id)),
            ).fetchone()
            return int(row["id"])

    def set_seller_decision(self, request_id: int, seller_user_id: str, accepted: bool) -> None:
        status = "ACCEPTED" if accepted else "REJECTED"
        qualification = "READY_FOR_BUYER" if accepted else "DECLINED"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET requester_status=?, qualification_status=?, updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (status, qualification, self._now(), int(request_id), str(seller_user_id)),
            )

    # Backward-compatible name used by older code/tests.
    def set_requester_consent(self, request_id: int, responder_user_id: str, accepted: bool) -> None:
        self.set_seller_decision(request_id, responder_user_id, accepted)

    def mark_waiting_address(self, request_id: int, seller_user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET qualification_status='WAITING_ADDRESS', updated_at=?
                WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'
                """,
                (self._now(), int(request_id), str(seller_user_id)),
            )

    def save_delivery_address(self, request_id: int, seller_user_id: str, address: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET delivery_address=?, qualification_status='QUALIFIED', converted_at=?, updated_at=?
                WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'
                """,
                (
                    str(address).strip(), self._now(), self._now(),
                    int(request_id), str(seller_user_id),
                ),
            )

    def mark_contact_shared(self, request_id: int, seller_user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET contact_shared=1, updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (self._now(), int(request_id), str(seller_user_id)),
            )

    def get_interest(self, request_id: int, seller_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (int(request_id), str(seller_user_id)),
            ).fetchone()
        return dict(row) if row else None

    def was_targeted(self, request_id: int, target_user_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM universal_notifications
                WHERE request_id=? AND target_user_id=? AND status='SENT'
                LIMIT 1
                """,
                (int(request_id), str(target_user_id)),
            ).fetchone()
        return row is not None

    def latest_sent_request_for_target(self, target_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT request_id, requester_user_id, target_user_id, created_at
                FROM universal_notifications
                WHERE target_user_id=? AND status='SENT'
                ORDER BY id DESC LIMIT 1
                """,
                (str(target_user_id),),
            ).fetchone()
        return dict(row) if row else None

    def latest_pending_interest_for_seller(self, seller_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM universal_interests
                WHERE responder_user_id=?
                  AND responder_status='INTERESTED'
                  AND requester_status='PENDING'
                  AND contact_shared=0
                ORDER BY id DESC LIMIT 1
                """,
                (str(seller_user_id),),
            ).fetchone()
        return dict(row) if row else None

    def latest_waiting_address_for_buyer(self, buyer_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM universal_interests
                WHERE requester_user_id=?
                  AND responder_status='INTERESTED'
                  AND requester_status='ACCEPTED'
                  AND qualification_status='WAITING_ADDRESS'
                  AND contact_shared=0
                ORDER BY id DESC LIMIT 1
                """,
                (str(buyer_user_id),),
            ).fetchone()
        return dict(row) if row else None

    def latest_ready_for_buyer(self, buyer_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM universal_interests
                WHERE requester_user_id=?
                  AND requester_status='ACCEPTED'
                  AND qualification_status='READY_FOR_BUYER'
                ORDER BY id DESC LIMIT 1
                """,
                (str(buyer_user_id),),
            ).fetchone()
        return dict(row) if row else None

    def latest_qualified_interest_for_buyer(self, buyer_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM universal_interests
                WHERE requester_user_id=?
                  AND requester_status='ACCEPTED'
                  AND qualification_status='QUALIFIED'
                ORDER BY id DESC LIMIT 1
                """,
                (str(buyer_user_id),),
            ).fetchone()
        return dict(row) if row else None

    # Compatibility wrappers for previous service names.
    def latest_pending_interest_for_requester(self, requester_user_id: str) -> Optional[Dict[str, Any]]:
        return self.latest_pending_interest_for_seller(requester_user_id)

    def latest_waiting_address_for_responder(self, responder_user_id: str) -> Optional[Dict[str, Any]]:
        return self.latest_waiting_address_for_buyer(responder_user_id)

    def latest_qualified_interest_for_responder(self, responder_user_id: str) -> Optional[Dict[str, Any]]:
        return self.latest_qualified_interest_for_buyer(responder_user_id)
