"""Persistent dedupe ledger for targeted buyer re-engagement alerts."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class ReengagementRepository:
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
                CREATE TABLE IF NOT EXISTS reengagement_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_user_id TEXT NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    demand_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(buyer_user_id, product_id, fingerprint)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reengagement_buyer ON reengagement_alerts(buyer_user_id, created_at)"
            )

    def claim(self, buyer_user_id: str, seller_user_id: str, demand_id: int,
              product_id: int, fingerprint: str) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO reengagement_alerts(
                        buyer_user_id,seller_user_id,demand_id,product_id,fingerprint,created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        str(buyer_user_id), str(seller_user_id), int(demand_id),
                        int(product_id), str(fingerprint), self._now(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def release(self, buyer_user_id: str, product_id: int, fingerprint: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM reengagement_alerts WHERE buyer_user_id=? AND product_id=? AND fingerprint=?",
                (str(buyer_user_id), int(product_id), str(fingerprint)),
            )
