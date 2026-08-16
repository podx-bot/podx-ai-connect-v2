"""SQLite persistence for PODX intercity ride sharing."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


class RideRepository:
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
                CREATE TABLE IF NOT EXISTS rides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_user_id TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    travel_date TEXT NOT NULL,
                    travel_time TEXT NOT NULL,
                    seats_total INTEGER NOT NULL,
                    seats_available INTEGER NOT NULL,
                    fare_per_seat REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rides_route_date
                ON rides(origin, destination, travel_date, status);
                CREATE TABLE IF NOT EXISTS ride_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ride_id INTEGER NOT NULL,
                    passenger_user_id TEXT NOT NULL,
                    seats INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'REQUESTED',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(ride_id, passenger_user_id, status)
                );
                CREATE INDEX IF NOT EXISTS idx_ride_bookings_ride
                ON ride_bookings(ride_id, status);
                """
            )

    def create_ride(self, driver_user_id: str, origin: str, destination: str, travel_date: str,
                    travel_time: str, seats: int, fare_per_seat: float | None = None) -> int:
        seats = max(1, int(seats))
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO rides(driver_user_id,origin,destination,travel_date,travel_time,
                                  seats_total,seats_available,fare_per_seat,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?, 'OPEN', ?, ?)
                """,
                (str(driver_user_id), origin.strip(), destination.strip(), travel_date.strip(),
                 travel_time.strip(), seats, seats, fare_per_seat, now, now),
            )
            return int(cur.lastrowid)

    def get_ride(self, ride_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM rides WHERE id=?", (int(ride_id),)).fetchone()
        return dict(row) if row else None

    def find_open(self, origin: str, destination: str, travel_date: str, limit: int = 10) -> list[dict[str, Any]]:
        origin_n = self._norm(origin); destination_n = self._norm(destination); date_n = self._norm(travel_date)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM rides WHERE status='OPEN' AND seats_available>0 ORDER BY id DESC LIMIT 100"""
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            if not self._same_place(origin_n, self._norm(data['origin'])):
                continue
            if not self._same_place(destination_n, self._norm(data['destination'])):
                continue
            if date_n and date_n != self._norm(data['travel_date']):
                continue
            result.append(data)
            if len(result) >= max(1, int(limit)):
                break
        return result

    def create_booking(self, ride_id: int, passenger_user_id: str, seats: int = 1) -> dict[str, Any]:
        ride = self.get_ride(int(ride_id))
        if not ride or str(ride.get('status')).upper() != 'OPEN':
            return {"status": "RIDE_NOT_OPEN"}
        seats = max(1, int(seats))
        if seats > int(ride.get('seats_available') or 0):
            return {"status": "NOT_ENOUGH_SEATS"}
        now = self._now()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO ride_bookings(ride_id,passenger_user_id,seats,status,created_at,updated_at)
                       VALUES(?,?,?,'REQUESTED',?,?)""",
                    (int(ride_id), str(passenger_user_id), seats, now, now),
                )
                booking_id = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            return {"status": "ALREADY_REQUESTED"}
        return {"status": "REQUESTED", "booking_id": booking_id, "ride_id": int(ride_id), "seats": seats}

    def get_booking(self, booking_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ride_bookings WHERE id=?", (int(booking_id),)).fetchone()
        return dict(row) if row else None

    def decide_booking(self, booking_id: int, driver_user_id: str, accept: bool) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            booking = conn.execute("SELECT * FROM ride_bookings WHERE id=?", (int(booking_id),)).fetchone()
            if not booking:
                conn.rollback(); return {"status": "NOT_FOUND"}
            ride = conn.execute("SELECT * FROM rides WHERE id=?", (int(booking['ride_id']),)).fetchone()
            if not ride or str(ride['driver_user_id']) != str(driver_user_id):
                conn.rollback(); return {"status": "NOT_DRIVER"}
            if str(booking['status']).upper() != 'REQUESTED':
                conn.rollback(); return {"status": str(booking['status']).upper()}
            if not accept:
                conn.execute("UPDATE ride_bookings SET status='REJECTED',updated_at=? WHERE id=?", (self._now(), int(booking_id)))
                conn.commit(); return {"status": "REJECTED", "booking": dict(booking), "ride": dict(ride)}
            seats = int(booking['seats'])
            available = int(ride['seats_available'])
            if seats > available or str(ride['status']).upper() != 'OPEN':
                conn.rollback(); return {"status": "NOT_ENOUGH_SEATS"}
            remaining = available - seats
            ride_status = 'FULL' if remaining <= 0 else 'OPEN'
            now = self._now()
            conn.execute("UPDATE ride_bookings SET status='ACCEPTED',updated_at=? WHERE id=?", (now, int(booking_id)))
            conn.execute("UPDATE rides SET seats_available=?,status=?,updated_at=? WHERE id=?", (remaining, ride_status, now, int(ride['id'])))
            conn.commit()
            return {"status": "ACCEPTED", "booking": dict(booking), "ride": {**dict(ride), "seats_available": remaining, "status": ride_status}}

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").casefold().strip().split())

    @staticmethod
    def _same_place(a: str, b: str) -> bool:
        return bool(a and b and (a == b or a in b or b in a))
