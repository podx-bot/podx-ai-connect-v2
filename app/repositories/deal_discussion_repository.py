"""Persistence for private buyer/seller deal discussion before contact sharing."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class DealDiscussionRepository:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS universal_deal_discussions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    buyer_question TEXT,
                    seller_note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(request_id, seller_user_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deal_buyer_status ON universal_deal_discussions(buyer_user_id,status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_deal_seller_status ON universal_deal_discussions(seller_user_id,status)"
            )

    def start(self, request_id, buyer, seller, details=None):
        now = self._now()
        payload = json.dumps(details or {}, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO universal_deal_discussions(
                    request_id,buyer_user_id,seller_user_id,status,details_json,
                    buyer_question,seller_note,created_at,updated_at
                ) VALUES(?,?,?,'WAITING_SELLER_DETAILS',?,NULL,NULL,?,?)
                ON CONFLICT(request_id,seller_user_id) DO UPDATE SET
                    buyer_user_id=excluded.buyer_user_id,
                    status='WAITING_SELLER_DETAILS',details_json=excluded.details_json,
                    buyer_question=NULL,seller_note=NULL,updated_at=excluded.updated_at
                """,
                (int(request_id), str(buyer), str(seller), payload, now, now),
            )
        return self.get(request_id, seller)

    def get(self, request_id, seller):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM universal_deal_discussions WHERE request_id=? AND seller_user_id=?",
                (int(request_id), str(seller)),
            ).fetchone()
        return self._row(row) if row else None

    def save_seller_details(self, request_id, seller, details, seller_note, revised=False):
        current = self.get(request_id, seller)
        if not current:
            return None
        merged = dict(current.get("details") or {})
        merged.update({k: v for k, v in (details or {}).items() if v not in (None, "")})
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_deal_discussions
                SET status='WAITING_BUYER_CONFIRM',details_json=?,seller_note=?,updated_at=?
                WHERE request_id=? AND seller_user_id=?
                """,
                (json.dumps(merged, ensure_ascii=False), str(seller_note or "").strip(), self._now(), int(request_id), str(seller)),
            )
        return self.get(request_id, seller)

    def mark_waiting_buyer_change(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_deal_discussions SET status='WAITING_BUYER_CHANGE',updated_at=? WHERE request_id=? AND seller_user_id=?",
                (self._now(), int(request_id), str(seller)),
            )

    def save_buyer_change(self, request_id, seller, question, details=None):
        current = self.get(request_id, seller)
        if not current:
            return None
        merged = dict(current.get("details") or {})
        merged.update({k: v for k, v in (details or {}).items() if v not in (None, "")})
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE universal_deal_discussions
                SET status='WAITING_SELLER_REVISION',buyer_question=?,details_json=?,updated_at=?
                WHERE request_id=? AND seller_user_id=?
                """,
                (
                    str(question or "").strip(),
                    json.dumps(merged, ensure_ascii=False),
                    self._now(),
                    int(request_id),
                    str(seller),
                ),
            )
        return self.get(request_id, seller)

    def confirm(self, request_id, seller):
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_deal_discussions SET status='CONFIRMED',updated_at=? WHERE request_id=? AND seller_user_id=?",
                (self._now(), int(request_id), str(seller)),
            )
        return self.get(request_id, seller)

    def latest_for_seller(self, seller, statuses):
        return self._latest("seller_user_id", seller, statuses)

    def latest_for_buyer(self, buyer, statuses):
        return self._latest("buyer_user_id", buyer, statuses)

    def _latest(self, column, user_id, statuses):
        states = tuple(str(x) for x in statuses)
        if not states:
            return None
        marks = ",".join("?" for _ in states)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM universal_deal_discussions WHERE {column}=? AND status IN ({marks}) ORDER BY updated_at DESC, id DESC LIMIT 1",
                (str(user_id), *states),
            ).fetchone()
        return self._row(row) if row else None

    @staticmethod
    def _row(row):
        data = dict(row)
        try:
            data["details"] = json.loads(data.pop("details_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            data["details"] = {}
        return data
