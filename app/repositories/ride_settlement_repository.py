"""Persistence for ride fare confirmation and zero-charge PODX settlement audit."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


class RideSettlementRepository:
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
                CREATE TABLE IF NOT EXISTS ride_settlements(
                    booking_id INTEGER PRIMARY KEY,
                    ride_id INTEGER NOT NULL,
                    driver_user_id TEXT NOT NULL,
                    passenger_user_id TEXT NOT NULL,
                    seats INTEGER NOT NULL DEFAULT 1,
                    quoted_fare_per_seat REAL,
                    quoted_total REAL,
                    final_fare REAL,
                    platform_charge REAL NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    driver_proposed_at TEXT,
                    passenger_confirmed_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ride_settlement_status
                ON ride_settlements(status, updated_at);
                """
            )

    def ensure(self, booking: dict[str, Any], ride: dict[str, Any]) -> dict[str, Any]:
        booking_id = int(booking["id"])
        seats = max(1, int(booking.get("seats") or 1))
        per_seat = ride.get("fare_per_seat")
        quoted_total = float(per_seat) * seats if per_seat is not None else None
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO ride_settlements(
                       booking_id,ride_id,driver_user_id,passenger_user_id,seats,
                       quoted_fare_per_seat,quoted_total,final_fare,platform_charge,
                       currency,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,0,'INR','OPEN',?,?)""",
                (
                    booking_id,
                    int(booking["ride_id"]),
                    str(ride.get("driver_user_id") or ""),
                    str(booking.get("passenger_user_id") or ""),
                    seats,
                    per_seat,
                    quoted_total,
                    quoted_total,
                    now,
                    now,
                ),
            )
        return self.get(booking_id) or {}

    def get(self, booking_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ride_settlements WHERE booking_id=?",
                (int(booking_id),),
            ).fetchone()
        return dict(row) if row else None

    def propose_final_fare(self, booking_id: int, amount: float) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE ride_settlements
                   SET final_fare=?, platform_charge=0, status='FARE_PROPOSED',
                       driver_proposed_at=?, passenger_confirmed_at=NULL, updated_at=?
                   WHERE booking_id=?""",
                (max(0.0, float(amount)), now, now, int(booking_id)),
            )
            if int(cur.rowcount or 0) == 0:
                return None
        return self.get(booking_id)

    def confirm_final_fare(self, booking_id: int) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE ride_settlements
                   SET status=CASE WHEN completed_at IS NULL THEN 'FARE_CONFIRMED' ELSE 'SETTLED' END,
                       platform_charge=0, passenger_confirmed_at=COALESCE(passenger_confirmed_at,?), updated_at=?
                   WHERE booking_id=? AND final_fare IS NOT NULL""",
                (now, now, int(booking_id)),
            )
            if int(cur.rowcount or 0) == 0:
                return None
        return self.get(booking_id)

    def mark_completed(self, booking_id: int) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE ride_settlements
                   SET completed_at=COALESCE(completed_at,?), platform_charge=0,
                       status=CASE WHEN passenger_confirmed_at IS NOT NULL THEN 'SETTLED' ELSE 'COMPLETED' END,
                       updated_at=?
                   WHERE booking_id=?""",
                (now, now, int(booking_id)),
            )
            if int(cur.rowcount or 0) == 0:
                return None
        return self.get(booking_id)
