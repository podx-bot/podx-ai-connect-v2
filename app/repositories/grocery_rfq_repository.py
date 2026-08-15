"""Smart Grocery/Kirana RFQ and seller quotation persistence."""
from __future__ import annotations
import re
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
                CREATE TABLE IF NOT EXISTS grocery_rfq_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'SENT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(rfq_id, seller_user_id)
                );
                CREATE INDEX IF NOT EXISTS idx_grocery_rfq_buyer ON grocery_rfqs(buyer_user_id, status, id);
                CREATE INDEX IF NOT EXISTS idx_grocery_target_seller ON grocery_rfq_targets(seller_user_id, status, id);
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

    def get_rfq(self, rfq_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM grocery_rfqs WHERE id=?", (int(rfq_id),)).fetchone()
        return dict(row) if row else None

    def latest_open_for_buyer(self, buyer_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM grocery_rfqs WHERE buyer_user_id=? AND status='OPEN' ORDER BY id DESC LIMIT 1", (str(buyer_user_id),)).fetchone()
        return dict(row) if row else None

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
            row = conn.execute("SELECT rfq_id,seller_user_id FROM grocery_quotes WHERE id=?", (int(quote_id),)).fetchone()
            if row:
                conn.execute("UPDATE grocery_rfq_targets SET status='QUOTED',updated_at=? WHERE rfq_id=? AND seller_user_id=?", (self._now(), int(row["rfq_id"]), str(row["seller_user_id"])))

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

    def add_target(self, rfq_id: int, seller_user_id: str) -> bool:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO grocery_rfq_targets(rfq_id,seller_user_id,status,created_at,updated_at) VALUES(?,?,'SENT',?,?)", (int(rfq_id), str(seller_user_id), now, now))
            return int(cur.rowcount or 0) > 0

    def target_for_seller(self, seller_user_id: str, rfq_id: int | None = None) -> Optional[Dict[str, Any]]:
        sql = """SELECT t.*,r.buyer_user_id,r.location_text FROM grocery_rfq_targets t JOIN grocery_rfqs r ON r.id=t.rfq_id WHERE t.seller_user_id=? AND t.status='SENT' AND r.status='OPEN'"""
        params: List[Any] = [str(seller_user_id)]
        if rfq_id is not None:
            sql += " AND t.rfq_id=?"; params.append(int(rfq_id))
        sql += " ORDER BY t.id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def find_candidate_sellers(self, items: List[Dict[str, Any]], exclude_user_id: str | None = None, limit: int = 12) -> List[Dict[str, Any]]:
        wanted = [self._norm(item.get("item_name") or item.get("name")) for item in items]
        wanted = [item for item in wanted if item]
        if not wanted:
            return []
        with self._connect() as conn:
            try:
                rows = conn.execute("SELECT seller_user_id,subject FROM seller_products WHERE active=1 ORDER BY updated_at DESC").fetchall()
            except sqlite3.OperationalError:
                return []
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            seller = str(row["seller_user_id"])
            if exclude_user_id is not None and seller == str(exclude_user_id):
                continue
            subject = self._norm(row["subject"])
            hits = sum(1 for wanted_item in wanted if self._similar(wanted_item, subject))
            if not hits:
                continue
            entry = result.setdefault(seller, {"seller_user_id": seller, "matched_items": 0})
            entry["matched_items"] += hits
        return sorted(result.values(), key=lambda row: (-int(row["matched_items"]), str(row["seller_user_id"])))[: max(1, int(limit))]

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(re.sub(r"[^\w\u0C00-\u0C7F\u0900-\u097F]+", " ", str(value or "").casefold()).split())

    @classmethod
    def _similar(cls, a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        at, bt = set(a.split()), set(b.split())
        return bool(at and bt and (len(at & bt) / max(1, min(len(at), len(bt)))) >= 0.6)
