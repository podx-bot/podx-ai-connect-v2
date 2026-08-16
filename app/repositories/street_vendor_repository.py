"""Persistence for mobile/street vendor presence and proximity alert dedupe."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


class StreetVendorRepository:
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
                CREATE TABLE IF NOT EXISTS street_vendor_profiles (
                    vendor_mobile TEXT PRIMARY KEY,
                    items_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    latitude REAL,
                    longitude REAL,
                    location_text TEXT,
                    last_location_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS street_vendor_alert_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor_mobile TEXT NOT NULL,
                    buyer_mobile TEXT NOT NULL,
                    demand_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    vendor_latitude REAL,
                    vendor_longitude REAL,
                    alerted_at TEXT NOT NULL,
                    UNIQUE(vendor_mobile, buyer_mobile, demand_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vendor_status ON street_vendor_profiles(status)")

    def enable(self, vendor_mobile: str, items_text: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO street_vendor_profiles(vendor_mobile, items_text, status, created_at, updated_at)
                VALUES (?, ?, 'ACTIVE', ?, ?)
                ON CONFLICT(vendor_mobile) DO UPDATE SET
                    items_text=excluded.items_text,
                    status='ACTIVE',
                    updated_at=excluded.updated_at
                """,
                (str(vendor_mobile), str(items_text).strip(), now, now),
            )
        return self.get(vendor_mobile) or {}

    def disable(self, vendor_mobile: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE street_vendor_profiles SET status='INACTIVE', updated_at=? WHERE vendor_mobile=?",
                (now, str(vendor_mobile)),
            )

    def update_location(self, vendor_mobile: str, latitude: float, longitude: float, location_text: str | None = None) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE street_vendor_profiles
                SET latitude=?, longitude=?, location_text=COALESCE(?, location_text),
                    last_location_at=?, updated_at=?
                WHERE vendor_mobile=? AND status='ACTIVE'
                """,
                (float(latitude), float(longitude), location_text, now, now, str(vendor_mobile)),
            )
        return self.get(vendor_mobile) if cur.rowcount else None

    def get(self, vendor_mobile: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM street_vendor_profiles WHERE vendor_mobile=?",
                (str(vendor_mobile),),
            ).fetchone()
        return dict(row) if row else None

    def alert_record(self, vendor_mobile: str, buyer_mobile: str, demand_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM street_vendor_alert_ledger
                WHERE vendor_mobile=? AND buyer_mobile=? AND demand_id=?
                """,
                (str(vendor_mobile), str(buyer_mobile), int(demand_id)),
            ).fetchone()
        return dict(row) if row else None

    def save_alert(self, vendor_mobile: str, buyer_mobile: str, demand_id: int, subject: str,
                   latitude: float, longitude: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO street_vendor_alert_ledger(
                    vendor_mobile,buyer_mobile,demand_id,subject,vendor_latitude,vendor_longitude,alerted_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(vendor_mobile,buyer_mobile,demand_id) DO UPDATE SET
                    subject=excluded.subject,
                    vendor_latitude=excluded.vendor_latitude,
                    vendor_longitude=excluded.vendor_longitude,
                    alerted_at=excluded.alerted_at
                """,
                (str(vendor_mobile), str(buyer_mobile), int(demand_id), str(subject), float(latitude), float(longitude), now),
            )
