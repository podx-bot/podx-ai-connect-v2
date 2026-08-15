"""Atomic local delivery/dispatch task persistence."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class LocalDispatchRepository:
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
                CREATE TABLE IF NOT EXISTS local_dispatch_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_ref TEXT NOT NULL UNIQUE,
                    seller_user_id TEXT NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    pickup_lat REAL,
                    pickup_lon REAL,
                    drop_lat REAL,
                    drop_lon REAL,
                    pickup_text TEXT,
                    drop_text TEXT,
                    fee REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    assigned_partner_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS local_dispatch_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    partner_user_id TEXT NOT NULL,
                    distance_km REAL,
                    status TEXT NOT NULL DEFAULT 'OFFERED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, partner_user_id)
                );
                """
            )

    def create_task(self, order_ref: str, seller_user_id: str, buyer_user_id: str, **data: Any) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO local_dispatch_tasks(order_ref,seller_user_id,buyer_user_id,pickup_lat,pickup_lon,drop_lat,drop_lon,pickup_text,drop_text,fee,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'OPEN',?,?)""",
                (str(order_ref), str(seller_user_id), str(buyer_user_id), data.get("pickup_lat"), data.get("pickup_lon"), data.get("drop_lat"), data.get("drop_lon"), data.get("pickup_text"), data.get("drop_text"), data.get("fee"), now, now),
            )
            return int(cur.lastrowid)

    def offer(self, task_id: int, partner_user_id: str, distance_km: float | None = None) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO local_dispatch_offers(task_id,partner_user_id,distance_km,status,created_at,updated_at) VALUES(?,?,?,'OFFERED',?,?)""",
                (int(task_id), str(partner_user_id), distance_km, now, now),
            )

    def claim(self, task_id: int, partner_user_id: str) -> bool:
        """First valid accepter wins. BEGIN IMMEDIATE serializes competing claims."""
        now = self._now()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute("SELECT status FROM local_dispatch_tasks WHERE id=?", (int(task_id),)).fetchone()
            if not task or task["status"] != "OPEN":
                conn.rollback()
                return False
            offer = conn.execute("SELECT status FROM local_dispatch_offers WHERE task_id=? AND partner_user_id=?", (int(task_id), str(partner_user_id))).fetchone()
            if not offer or offer["status"] != "OFFERED":
                conn.rollback()
                return False
            conn.execute("UPDATE local_dispatch_tasks SET status='ACCEPTED',assigned_partner_id=?,updated_at=? WHERE id=?", (str(partner_user_id), now, int(task_id)))
            conn.execute("UPDATE local_dispatch_offers SET status=CASE WHEN partner_user_id=? THEN 'ACCEPTED' ELSE 'CLOSED' END,updated_at=? WHERE task_id=?", (str(partner_user_id), now, int(task_id)))
            conn.commit()
            return True
        finally:
            conn.close()

    def update_status(self, task_id: int, partner_user_id: str, status: str) -> bool:
        allowed = {"PICKED_UP", "ON_THE_WAY", "DELIVERED", "CANCELLED"}
        new_status = str(status).upper()
        if new_status not in allowed:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE local_dispatch_tasks SET status=?,updated_at=? WHERE id=? AND assigned_partner_id=?",
                (new_status, self._now(), int(task_id), str(partner_user_id)),
            )
            return cur.rowcount == 1

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM local_dispatch_tasks WHERE id=?", (int(task_id),)).fetchone()
        return dict(row) if row else None
