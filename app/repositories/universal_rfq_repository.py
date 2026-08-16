"""Domain-neutral RFQ persistence for products, catering, services and events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class UniversalRFQRepository:
    VALID_TYPES = {"GROCERY", "CATERING", "PRODUCT", "SERVICE", "EVENT", "OTHER"}

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
                CREATE TABLE IF NOT EXISTS universal_rfqs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requester_user_id TEXT NOT NULL,
                    rfq_type TEXT NOT NULL,
                    title TEXT,
                    location_text TEXT,
                    event_date TEXT,
                    guest_count INTEGER,
                    budget REAL,
                    metadata_json TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    selected_quote_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS universal_rfq_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    category TEXT,
                    quantity REAL,
                    unit TEXT,
                    required INTEGER NOT NULL DEFAULT 1,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(rfq_id, item_name, category)
                );
                CREATE TABLE IF NOT EXISTS universal_rfq_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    match_score REAL,
                    distance_km REAL,
                    status TEXT NOT NULL DEFAULT 'SENT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(rfq_id, provider_user_id)
                );
                CREATE TABLE IF NOT EXISTS universal_rfq_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfq_id INTEGER NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    service_fee REAL NOT NULL DEFAULT 0,
                    delivery_fee REAL NOT NULL DEFAULT 0,
                    provider_total REAL,
                    reliability_score REAL NOT NULL DEFAULT 0.5,
                    notes TEXT,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(rfq_id, provider_user_id)
                );
                CREATE TABLE IF NOT EXISTS universal_rfq_quote_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    quote_id INTEGER NOT NULL,
                    rfq_item_id INTEGER NOT NULL,
                    unit_price REAL,
                    line_total REAL,
                    available INTEGER NOT NULL DEFAULT 1,
                    included INTEGER NOT NULL DEFAULT 1,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(quote_id, rfq_item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_urfq_requester ON universal_rfqs(requester_user_id, status, id);
                CREATE INDEX IF NOT EXISTS idx_urfq_target_provider ON universal_rfq_targets(provider_user_id, status, id);
                CREATE INDEX IF NOT EXISTS idx_urfq_quote_rfq ON universal_rfq_quotes(rfq_id, status, id);
                """
            )

    def create_rfq(
        self,
        requester_user_id: str,
        rfq_type: str,
        items: List[Dict[str, Any]],
        title: str | None = None,
        location_text: str | None = None,
        event_date: str | None = None,
        guest_count: int | None = None,
        budget: float | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        kind = str(rfq_type or "OTHER").strip().upper()
        if kind not in self.VALID_TYPES:
            kind = "OTHER"
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO universal_rfqs(
                       requester_user_id,rfq_type,title,location_text,event_date,guest_count,budget,metadata_json,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,'OPEN',?,?)""",
                (
                    str(requester_user_id), kind, self._clean(title), self._clean(location_text),
                    self._clean(event_date), int(guest_count) if guest_count is not None else None,
                    float(budget) if budget is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False), now, now,
                ),
            )
            rfq_id = int(cur.lastrowid)
            for item in items or []:
                self._insert_item(conn, rfq_id, item, now)
            return rfq_id

    def _insert_item(self, conn, rfq_id: int, item: Dict[str, Any], now: str) -> None:
        name = self._clean(item.get("item_name") or item.get("name"))
        if not name:
            return
        conn.execute(
            """INSERT OR IGNORE INTO universal_rfq_items(
                   rfq_id,item_name,category,quantity,unit,required,metadata_json,created_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                int(rfq_id), name, self._clean(item.get("category")), item.get("quantity"), self._clean(item.get("unit")),
                1 if item.get("required", True) else 0,
                json.dumps(item.get("metadata") or {}, ensure_ascii=False), now,
            ),
        )

    def get_rfq(self, rfq_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM universal_rfqs WHERE id=?", (int(rfq_id),)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["metadata"] = self._json(data.pop("metadata_json", None))
        return data

    def list_items(self, rfq_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM universal_rfq_items WHERE rfq_id=? ORDER BY id", (int(rfq_id),)).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["metadata"] = self._json(data.pop("metadata_json", None))
            result.append(data)
        return result

    def add_target(self, rfq_id: int, provider_user_id: str, match_score: float | None = None, distance_km: float | None = None) -> bool:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO universal_rfq_targets(
                       rfq_id,provider_user_id,match_score,distance_km,status,created_at,updated_at
                   ) VALUES(?,?,?,?,'SENT',?,?)""",
                (int(rfq_id), str(provider_user_id), match_score, distance_km, now, now),
            )
            return int(cur.rowcount or 0) > 0

    def target_for_provider(self, provider_user_id: str, rfq_id: int | None = None) -> Optional[Dict[str, Any]]:
        sql = """SELECT t.*,r.rfq_type,r.title,r.location_text,r.event_date,r.guest_count
                 FROM universal_rfq_targets t JOIN universal_rfqs r ON r.id=t.rfq_id
                 WHERE t.provider_user_id=? AND t.status='SENT' AND r.status='OPEN'"""
        params: List[Any] = [str(provider_user_id)]
        if rfq_id is not None:
            sql += " AND t.rfq_id=?"
            params.append(int(rfq_id))
        sql += " ORDER BY t.id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def start_quote(
        self,
        rfq_id: int,
        provider_user_id: str,
        service_fee: float = 0,
        delivery_fee: float = 0,
        provider_total: float | None = None,
        reliability_score: float = 0.5,
        notes: str | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO universal_rfq_quotes(
                       rfq_id,provider_user_id,service_fee,delivery_fee,provider_total,reliability_score,notes,status,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,'DRAFT',?,?)
                   ON CONFLICT(rfq_id,provider_user_id) DO UPDATE SET
                       service_fee=excluded.service_fee,delivery_fee=excluded.delivery_fee,
                       provider_total=excluded.provider_total,reliability_score=excluded.reliability_score,
                       notes=excluded.notes,updated_at=excluded.updated_at""",
                (
                    int(rfq_id), str(provider_user_id), float(service_fee or 0), float(delivery_fee or 0),
                    float(provider_total) if provider_total is not None else None,
                    float(reliability_score or 0.5), self._clean(notes), now, now,
                ),
            )
            row = conn.execute("SELECT id FROM universal_rfq_quotes WHERE rfq_id=? AND provider_user_id=?", (int(rfq_id), str(provider_user_id))).fetchone()
            return int(row["id"])

    def set_item_quote(
        self,
        quote_id: int,
        rfq_item_id: int,
        unit_price: float | None = None,
        line_total: float | None = None,
        available: bool = True,
        included: bool = True,
        note: str | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO universal_rfq_quote_items(
                       quote_id,rfq_item_id,unit_price,line_total,available,included,note,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(quote_id,rfq_item_id) DO UPDATE SET
                       unit_price=excluded.unit_price,line_total=excluded.line_total,available=excluded.available,
                       included=excluded.included,note=excluded.note,updated_at=excluded.updated_at""",
                (
                    int(quote_id), int(rfq_item_id), unit_price, line_total,
                    1 if available else 0, 1 if included else 0, self._clean(note), now, now,
                ),
            )

    def submit_quote(self, quote_id: int) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute("UPDATE universal_rfq_quotes SET status='SUBMITTED',updated_at=? WHERE id=?", (now, int(quote_id)))
            quote = conn.execute("SELECT rfq_id,provider_user_id FROM universal_rfq_quotes WHERE id=?", (int(quote_id),)).fetchone()
            if quote:
                conn.execute(
                    "UPDATE universal_rfq_targets SET status='QUOTED',updated_at=? WHERE rfq_id=? AND provider_user_id=?",
                    (now, int(quote["rfq_id"]), str(quote["provider_user_id"])),
                )

    def submitted_quotes(self, rfq_id: int) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            quotes = conn.execute("SELECT * FROM universal_rfq_quotes WHERE rfq_id=? AND status='SUBMITTED' ORDER BY id", (int(rfq_id),)).fetchall()
            result = []
            for quote in quotes:
                data = dict(quote)
                rows = conn.execute(
                    """SELECT qi.*,ri.item_name,ri.category,ri.quantity,ri.unit,ri.required
                       FROM universal_rfq_quote_items qi JOIN universal_rfq_items ri ON ri.id=qi.rfq_item_id
                       WHERE qi.quote_id=? ORDER BY ri.id""",
                    (int(quote["id"]),),
                ).fetchall()
                data["items"] = [dict(row) for row in rows]
                result.append(data)
            return result

    def select_quote(self, rfq_id: int, quote_id: int, requester_user_id: str) -> bool:
        now = self._now()
        with self._connect() as conn:
            quote = conn.execute(
                "SELECT id FROM universal_rfq_quotes WHERE id=? AND rfq_id=? AND status='SUBMITTED'",
                (int(quote_id), int(rfq_id)),
            ).fetchone()
            if not quote:
                return False
            cur = conn.execute(
                """UPDATE universal_rfqs SET status='SELECTED',selected_quote_id=?,updated_at=?
                   WHERE id=? AND requester_user_id=? AND status='OPEN'""",
                (int(quote_id), now, int(rfq_id), str(requester_user_id)),
            )
            return cur.rowcount == 1

    @staticmethod
    def _clean(value: Any) -> str | None:
        text = " ".join(str(value or "").strip().split())
        return text or None

    @staticmethod
    def _json(value: Any) -> Dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
