"""Persistence for selected grocery RFQ quotes and delivery handoff state."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class GroceryOrderRepository:
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS grocery_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL UNIQUE,
                    quote_id INTEGER NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    quote_total REAL NOT NULL,
                    quoted_delivery_fee REAL DEFAULT 0,
                    delivery_address TEXT,
                    dispatch_task_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'ADDRESS_REQUIRED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_grocery_orders_buyer ON grocery_orders(buyer_user_id, status, id);
                """
            )

    def create_from_quote(self, rfq_id: int, quote_id: int, buyer_user_id: str, seller_user_id: str,
                          quote_total: float, quoted_delivery_fee: float = 0) -> int:
        now = self._now()
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM grocery_orders WHERE rfq_id=?", (int(rfq_id),)).fetchone()
            if existing:
                return int(existing["id"])
            cur = conn.execute(
                """INSERT INTO grocery_orders(rfq_id,quote_id,buyer_user_id,seller_user_id,quote_total,quoted_delivery_fee,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'ADDRESS_REQUIRED',?,?)""",
                (int(rfq_id), int(quote_id), str(buyer_user_id), str(seller_user_id), float(quote_total), float(quoted_delivery_fee or 0), now, now),
            )
            conn.execute("UPDATE grocery_rfqs SET status='SELECTED',updated_at=? WHERE id=? AND status='OPEN'", (now, int(rfq_id)))
            return int(cur.lastrowid)

    def get(self, order_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM grocery_orders WHERE id=?", (int(order_id),)).fetchone()
        return dict(row) if row else None

    def set_delivery_address(self, order_id: int, buyer_user_id: str, address: str) -> bool:
        clean = " ".join(str(address or "").strip().split())
        if not clean:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE grocery_orders SET delivery_address=?,status='READY_FOR_DISPATCH',updated_at=?
                   WHERE id=? AND buyer_user_id=? AND status='ADDRESS_REQUIRED'""",
                (clean, self._now(), int(order_id), str(buyer_user_id)),
            )
            return cur.rowcount == 1

    def attach_dispatch(self, order_id: int, task_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE grocery_orders SET dispatch_task_id=?,status='DISPATCH_OPEN',updated_at=?
                   WHERE id=? AND status='READY_FOR_DISPATCH'""",
                (int(task_id), self._now(), int(order_id)),
            )
            return cur.rowcount == 1
