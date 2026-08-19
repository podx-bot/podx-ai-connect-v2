"""Persistence for seller-interest WhatsApp delivery receipts and retries."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class SellerInterestDeliveryRepository:
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
                CREATE TABLE IF NOT EXISTS seller_interest_deliveries(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    seller_mobile TEXT NOT NULL,
                    buyer_mobile TEXT,
                    fallback_body TEXT NOT NULL,
                    provider_message_id TEXT,
                    channel TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACCEPTED',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seller_interest_provider ON seller_interest_deliveries(provider_message_id)"
            )

    def record(self, *, request_id, buyer_user_id, seller_user_id, seller_mobile, buyer_mobile,
               fallback_body, provider_message_id, channel, retry_count=0, status="ACCEPTED"):
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO seller_interest_deliveries(
                    request_id,buyer_user_id,seller_user_id,seller_mobile,buyer_mobile,
                    fallback_body,provider_message_id,channel,status,retry_count,error_message,
                    created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,NULL,?,?)
                """,
                (
                    int(request_id), str(buyer_user_id), str(seller_user_id), str(seller_mobile),
                    str(buyer_mobile or ""), str(fallback_body), str(provider_message_id or ""),
                    str(channel), str(status), int(retry_count), now, now,
                ),
            )
            return cur.lastrowid

    def by_provider_message_id(self, provider_message_id):
        provider_message_id = str(provider_message_id or "").strip()
        if not provider_message_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM seller_interest_deliveries WHERE provider_message_id=? ORDER BY id DESC LIMIT 1",
                (provider_message_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_status(self, delivery_id, status, error_message=None):
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE seller_interest_deliveries
                SET status=?,error_message=?,updated_at=? WHERE id=?
                """,
                (str(status), str(error_message or ""), self._now(), int(delivery_id)),
            )
