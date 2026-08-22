"""Persistence for universal NEED/OFFER records.

This repository intentionally stays domain-neutral: work, workers, services,
products and future request types use the same storage model.

Important: this storage uses its own table name. The older DemandRepository
already owns `universal_demands` with a different schema, so sharing that table
causes startup failures on both fresh and existing databases.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class UniversalDemandRepository:
    TABLE = "universal_need_offer_records"

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
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
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
                    constraints_json TEXT NOT NULL DEFAULT '{{}}',
                    source TEXT NOT NULL DEFAULT 'text',
                    media_ref TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_need_offer_side_status ON {self.TABLE}(side, status)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_need_offer_domain_status ON {self.TABLE}(domain, status)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_need_offer_user_status ON {self.TABLE}(user_id, status)"
            )

    def create(self, record: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        constraints = record.get("constraints") or {}
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {self.TABLE} (
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
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ?", (demand_id,)
            ).fetchone()
        return self._row(row) if row else None

    def latest_active_for_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM {self.TABLE}
                WHERE user_id = ? AND status = 'ACTIVE'
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(user_id),),
            ).fetchone()
        return self._row(row) if row else None

    def latest_active_for_user_missing_location(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM {self.TABLE}
                WHERE user_id = ?
                  AND status = 'ACTIVE'
                  AND latitude IS NULL
                  AND longitude IS NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (str(user_id),),
            ).fetchone()
        return self._row(row) if row else None

    def update_location_text(self, demand_id: int, location_text: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE {self.TABLE}
                SET location_text = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(location_text).strip(), now, int(demand_id)),
            )

    def update_location(
        self,
        demand_id: int,
        latitude: float,
        longitude: float,
        location_text: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE {self.TABLE}
                SET latitude = ?, longitude = ?, location_text = COALESCE(?, location_text), updated_at = ?
                WHERE id = ?
                """,
                (float(latitude), float(longitude), location_text, now, int(demand_id)),
            )

    def list_active(self, limit: int = 500, exclude_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = f"SELECT * FROM {self.TABLE} WHERE status = 'ACTIVE'"
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
        sql = f"SELECT * FROM {self.TABLE} WHERE side = ? AND status = 'ACTIVE'"
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
                f"UPDATE {self.TABLE} SET status = ?, updated_at = ? WHERE id = ?",
                (status.upper(), now, demand_id),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["constraints"] = json.loads(data.pop("constraints_json") or "{}")
        return data
