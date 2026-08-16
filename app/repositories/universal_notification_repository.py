"""Persistence for universal targeted notifications and lead conversion."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class UniversalNotificationRepository:
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

    def _ensure_schema(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS universal_notifications(
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
                    UNIQUE(request_id,target_user_id)
                );
                CREATE TABLE IF NOT EXISTS universal_interests(
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
                    UNIQUE(request_id,responder_user_id)
                );
                """
            )
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(universal_interests)")}
            for name, sql in (
                ("qualification_status", "TEXT NOT NULL DEFAULT 'NEW'"),
                ("delivery_address", "TEXT"),
                ("converted_at", "TEXT"),
            ):
                if name not in cols:
                    conn.execute(f"ALTER TABLE universal_interests ADD COLUMN {name} {sql}")

    def reserve_notification(
        self,
        request_id,
        requester_user_id,
        target_user_id,
        wave=1,
        distance_km=None,
        relevance_score=None,
    ):
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO universal_notifications(
                        request_id,requester_user_id,target_user_id,wave,distance_km,relevance_score,
                        status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,'PENDING',?,?)
                    """,
                    (
                        request_id,
                        str(requester_user_id),
                        str(target_user_id),
                        wave,
                        distance_km,
                        relevance_score,
                        self._now(),
                        self._now(),
                    ),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def mark_sent(self, notification_id, provider_message_id=None):
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_notifications SET status='SENT',provider_message_id=?,updated_at=? WHERE id=?",
                (provider_message_id, self._now(), notification_id),
            )

    def mark_failed(self, notification_id):
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_notifications SET status='FAILED',updated_at=? WHERE id=?",
                (self._now(), notification_id),
            )

    def contacted_user_ids(self, request_id):
        with self._connect() as conn:
            return [
                str(row["target_user_id"])
                for row in conn.execute(
                    "SELECT target_user_id FROM universal_notifications WHERE request_id=?",
                    (request_id,),
                )
            ]

    def record_interest(self, request_id, buyer, seller):
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO universal_interests(
                    request_id,requester_user_id,responder_user_id,responder_status,
                    requester_status,contact_shared,qualification_status,created_at,updated_at
                ) VALUES(?,?,?,'INTERESTED','PENDING',0,'NEW',?,?)
                ON CONFLICT(request_id,responder_user_id) DO UPDATE SET
                    requester_user_id=excluded.requester_user_id,
                    responder_status='INTERESTED',requester_status='PENDING',qualification_status='NEW',
                    delivery_address=NULL,converted_at=NULL,updated_at=excluded.updated_at
                """,
                (request_id, str(buyer), str(seller), now, now),
            )
            return conn.execute(
                "SELECT id FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (request_id, str(seller)),
            ).fetchone()["id"]

    def set_seller_decision(self, request_id, seller, accepted):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET requester_status=?,qualification_status=?,updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (
                    "ACCEPTED" if accepted else "REJECTED",
                    "READY_FOR_BUYER" if accepted else "DECLINED",
                    self._now(),
                    request_id,
                    str(seller),
                ),
            )

    def set_requester_consent(self, request_id, responder_user_id, accepted):
        self.set_seller_decision(request_id, responder_user_id, accepted)

    def mark_waiting_address(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests SET qualification_status='WAITING_ADDRESS',updated_at=?
                WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'
                """,
                (self._now(), request_id, str(seller)),
            )

    def save_delivery_address(self, request_id, seller, address):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET delivery_address=?,qualification_status='WAITING_FINAL_CONFIRM',converted_at=NULL,updated_at=?
                WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'
                """,
                (str(address).strip(), self._now(), request_id, str(seller)),
            )

    def confirm_order(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET qualification_status='CONVERTED',converted_at=?,updated_at=?
                WHERE request_id=? AND responder_user_id=? AND requester_status='ACCEPTED'
                  AND qualification_status='WAITING_FINAL_CONFIRM'
                """,
                (self._now(), self._now(), request_id, str(seller)),
            )

    def cancel_order(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_interests
                SET qualification_status='CANCELLED',converted_at=NULL,updated_at=?
                WHERE request_id=? AND responder_user_id=?
                """,
                (self._now(), request_id, str(seller)),
            )

    def mark_contact_shared(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_interests SET contact_shared=1,updated_at=? WHERE request_id=? AND responder_user_id=?",
                (self._now(), request_id, str(seller)),
            )

    def get_interest(self, request_id, seller):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_interests WHERE request_id=? AND responder_user_id=?",
                (request_id, str(seller)),
            ).fetchone()
            return dict(row) if row else None

    def was_targeted(self, request_id, target):
        with self._connect() as conn:
            return (
                conn.execute(
                    """
                    SELECT 1 FROM universal_notifications
                    WHERE request_id=? AND target_user_id=? AND status='SENT' LIMIT 1
                    """,
                    (request_id, str(target)),
                ).fetchone()
                is not None
            )

    def latest_sent_request_for_target(self, target):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT request_id,requester_user_id,target_user_id,created_at
                FROM universal_notifications
                WHERE target_user_id=? AND status='SENT'
                ORDER BY id DESC LIMIT 1
                """,
                (str(target),),
            ).fetchone()
            return dict(row) if row else None

    def _latest(self, where, args):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_interests WHERE " + where + " ORDER BY id DESC LIMIT 1",
                args,
            ).fetchone()
            return dict(row) if row else None

    def latest_interest_for_buyer(self, buyer):
        return self._latest(
            "requester_user_id=? AND responder_status='INTERESTED' AND qualification_status NOT IN ('DECLINED','CANCELLED')",
            (str(buyer),),
        )

    def latest_pending_interest_for_seller(self, seller):
        return self._latest(
            "responder_user_id=? AND responder_status='INTERESTED' AND requester_status='PENDING' AND contact_shared=0",
            (str(seller),),
        )

    def latest_pending_interest_for_requester(self, requester):
        return self._latest(
            "requester_user_id=? AND responder_status='INTERESTED' AND requester_status='PENDING' AND contact_shared=0",
            (str(requester),),
        )

    def latest_waiting_address_for_buyer(self, buyer):
        return self._latest(
            "requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='WAITING_ADDRESS'",
            (str(buyer),),
        )

    def latest_waiting_final_confirm_for_buyer(self, buyer):
        return self._latest(
            "requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='WAITING_FINAL_CONFIRM'",
            (str(buyer),),
        )

    def latest_ready_for_buyer(self, buyer):
        return self._latest(
            "requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='READY_FOR_BUYER'",
            (str(buyer),),
        )

    def latest_qualified_interest_for_buyer(self, buyer):
        return self._latest(
            "requester_user_id=? AND requester_status='ACCEPTED' AND qualification_status='CONVERTED'",
            (str(buyer),),
        )

    def latest_waiting_address_for_responder(self, responder):
        return self.latest_waiting_address_for_buyer(responder)

    def latest_qualified_interest_for_responder(self, responder):
        return self.latest_qualified_interest_for_buyer(responder)
