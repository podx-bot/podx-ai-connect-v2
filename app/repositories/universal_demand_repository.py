"""Persistence for universal NEED/OFFER records.

This repository intentionally stays domain-neutral: work, workers, services,
products and future request types use the same storage model.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class UniversalDemandRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS universal_demands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    quantity REAL,
                    unit TEXT,
                    price REAL,
                    currency TEXT,
                    when_text TEXT,
                    latitude REAL,
                    longitude REAL,
                    location_text TEXT,
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'text',
                    media_ref TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_universal_side_status ON universal_demands(side, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_universal_domain_status ON universal_demands(domain, status)"
            )

    def create(self, record: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        constraints = record.get("constraints") or {}
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO universal_demands (
                    user_id, side, domain, subject, quantity, unit, price,
                    currency, when_text, latitude, longitude, location_text,
                    constraints_json, source, media_ref, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record["user_id"]), str(record["side"]).upper(),
                    str(record.get("domain") or "OTHER").upper(),
                    str(record["subject"]).strip(), record.get("quantity"),
                    record.get("unit"), record.get("price"),
                    record.get("currency"), record.get("when") or record.get("when_text"),
                    record.get("latitude"), record.get("longitude"),
                    record.get("location_text"), json.dumps(constraints, ensure_ascii=False),
                    record.get("source") or "text", record.get("media_ref"),
                    record.get("status") or "ACTIVE", now, now,
                ),
            )
            return int(cur.lastrowid)

    def get(self, demand_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM universal_demands WHERE id = ?", (demand_id,)).fetchone()
        return self._row(row) if row else None

    def list_active(self, limit: int = 500, exclude_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM universal_demands WHERE status = 'ACTIVE'"
        params: List[Any] = []
        if exclude_user_id is not None:
            sql += " AND user_id <> ?"
            params.append(str(exclude_user_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def list_opposite_active(self, side: str, domain: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        opposite = "OFFER" if str(side).upper() == "NEED" else "NEED"
        sql = "SELECT * FROM universal_demands WHERE side = ? AND status = 'ACTIVE'"
        params: List[Any] = [opposite]
        if domain:
            sql += " AND domain = ?"
            params.append(str(domain).upper())
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def update_status(self, demand_id: int, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE universal_demands SET status = ?, updated_at = ? WHERE id = ?",
                (status.upper(), now, demand_id),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["constraints"] = json.loads(data.pop("constraints_json") or "{}")
        return data
