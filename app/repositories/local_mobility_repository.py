"""Persistence for PODX local Bike Taxi and Parcel jobs."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone


class LocalMobilityRepository:
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
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS local_mobility_jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_user_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                pickup_text TEXT NOT NULL,
                drop_text TEXT NOT NULL,
                pickup_lat REAL,
                pickup_lon REAL,
                note TEXT,
                assigned_rider_id TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_local_mobility_open
                ON local_mobility_jobs(status, job_type, id);
            CREATE TABLE IF NOT EXISTS local_mobility_offers(
                job_id INTEGER NOT NULL,
                rider_user_id TEXT NOT NULL,
                distance_km REAL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(job_id, rider_user_id)
            );
            """)

    def create(self, requester_user_id: str, job_type: str, pickup_text: str,
               drop_text: str, pickup_lat=None, pickup_lon=None, note: str | None = None) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO local_mobility_jobs(
                    requester_user_id,job_type,pickup_text,drop_text,pickup_lat,pickup_lon,note,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,'OPEN',?,?)""",
                (str(requester_user_id), str(job_type).upper(), pickup_text.strip(), drop_text.strip(),
                 pickup_lat, pickup_lon, note, now, now),
            )
            return int(cur.lastrowid)

    def get(self, job_id: int):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM local_mobility_jobs WHERE id=?", (int(job_id),)).fetchone()
        return dict(row) if row else None

    def offer(self, job_id: int, rider_user_id: str, distance_km=None) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO local_mobility_offers(job_id,rider_user_id,distance_km,created_at) VALUES(?,?,?,?)",
                    (int(job_id), str(rider_user_id), distance_km, self._now()),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def claim(self, job_id: int, rider_user_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            offer = conn.execute(
                "SELECT 1 FROM local_mobility_offers WHERE job_id=? AND rider_user_id=?",
                (int(job_id), str(rider_user_id)),
            ).fetchone()
            if not offer:
                conn.rollback(); return False
            row = conn.execute("SELECT status FROM local_mobility_jobs WHERE id=?", (int(job_id),)).fetchone()
            if not row or str(row["status"]).upper() != "OPEN":
                conn.rollback(); return False
            cur = conn.execute(
                "UPDATE local_mobility_jobs SET assigned_rider_id=?,status='ASSIGNED',updated_at=? WHERE id=? AND status='OPEN'",
                (str(rider_user_id), self._now(), int(job_id)),
            )
            conn.commit()
            return int(cur.rowcount or 0) == 1

    def update_status(self, job_id: int, rider_user_id: str, next_status: str) -> bool:
        allowed = {
            "PICKED_UP": {"ASSIGNED"},
            "ON_THE_WAY": {"PICKED_UP"},
            "COMPLETED": {"PICKED_UP", "ON_THE_WAY"},
        }
        target = str(next_status).upper()
        if target not in allowed:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status,assigned_rider_id FROM local_mobility_jobs WHERE id=?", (int(job_id),)
            ).fetchone()
            if not row or str(row["assigned_rider_id"] or "") != str(rider_user_id):
                return False
            if str(row["status"]).upper() not in allowed[target]:
                return False
            cur = conn.execute(
                "UPDATE local_mobility_jobs SET status=?,updated_at=? WHERE id=?",
                (target, self._now(), int(job_id)),
            )
            return int(cur.rowcount or 0) == 1
