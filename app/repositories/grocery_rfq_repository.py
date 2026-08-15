"""Smart Grocery/Kirana RFQ and seller quotation persistence."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class GroceryRFQRepository:
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
                CREATE TABLE IF NOT EXISTS grocery_rfqs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buyer_user_id TEXT NOT NULL,
                    location_text TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS grocery_rfq_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity REAL,
                    unit TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS grocery_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    rating REAL,
                    distance_km REAL,
                    delivery_fee REAL DEFAULT 0,
                    reliability_score REAL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(rfq_id, seller_user_id)
                );
                CREATE TABLE IF NOT EXISTS grocery_quote_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_id INTEGER NOT NULL,
                    rfq_item_id INTEGER NOT NULL,
                    price REAL,
                    available INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(quote_id, rfq_item_id)
                );
                """
            )

    def create_rfq(self, buyer_user_id: str, items: List[Dict[str, Any]], location_text: str | None = None) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute("INSERT INTO grocery_rfqs(buyer_user_id,location_text,status,created_at,updated_at) VALUES(?,?,'OPEN',?,?)", (str(buyer_user_id), location_text, now, now))
            rfq_id = int(cur.lastrowid)
            for item in items:
                name = " ".join(str(item.get("item_name") or item.get("name") or "").strip().split())
                if not name:
                    continue
                conn.execute("INSERT INTO grocery_rfq_items(rfq_id,item_name,quantity,unit,created_at) VALUES(?,?,?,?,?)", (rfq_id, name, item.get("quantity"), item.get("unit"), now))
            return rfq_id

    def list_items(self, rfq_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM grocery_rfq_items WHERE rfq_id=? ORDER BY id", (int(rfq_id),)).fetchall()
        return [dict(row) for row in rows]

    def start_quote(self, rfq_id: int, seller_user_id: str, rating: float | None = None, distance_km: float | None = None, delivery_fee: float = 0, reliability_score: float = 0.5) -> int:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO grocery_quotes(rfq_id,seller_user_id,rating,distance_km,delivery_fee,reliability_score,status,created_at,updated_at) VALUES(?,?,?,?,?,?,'DRAFT',?,?) ON CONFLICT(rfq_id,seller_user_id) DO UPDATE SET rating=excluded.rating,distance_km=excluded.distance_km,delivery_fee=excluded.delivery_fee,reliability_score=excluded.reliability_score,updated_at=excluded.updated_at""",
                (int(rfq_id), str(seller_user_id), rating, distance_km, delivery_fee, reliability_score, now, now),
            )
            row = conn.execute("SELECT id FROM grocery_quotes WHERE rfq_id=? AND seller_user_id=?", (int(rfq_id), str(seller_user_id))).fetchone()
            return int(row["id"])

    def set_item_quote(self, quote_id: int, rfq_item_id: int, price: float | None, available: bool = True) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO grocery_quote_items(quote_id,rfq_item_id,price,available,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(quote_id,rfq_item_id) DO UPDATE SET price=excluded.price,available=excluded.available,updated_at=excluded.updated_at""",
                (int(quote_id), int(rfq_item_id), price, 1 if available else 0, now, now),
            )

    def submit_quote(self, quote_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE grocery_quotes SET status='SUBMITTED',updated_at=? WHERE id=?", (self._now(), int(quote_id)))

    def submitted_quotes(self, rfq_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            quotes = conn.execute("SELECT * FROM grocery_quotes WHERE rfq_id=? AND status='SUBMITTED'", (int(rfq_id),)).fetchall()
            result = []
            for quote in quotes:
                data = dict(quote)
                rows = conn.execute(
                    """SELECT qi.*,ri.item_name,ri.quantity,ri.unit FROM grocery_quote_items qi JOIN grocery_rfq_items ri ON ri.id=qi.rfq_item_id WHERE qi.quote_id=?""",
                    (int(quote["id"]),),
                ).fetchall()
                data["items"] = [dict(row) for row in rows]
                result.append(data)
            return result
