"""Read-only operational monitoring for PODX administrators."""
from __future__ import annotations

import sqlite3
from typing import Any


class AdminMonitoringService:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _table_exists(conn, name: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    @staticmethod
    def _count(conn, table: str, where: str = "1=1", params: tuple[Any, ...] = ()) -> int:
        if not AdminMonitoringService._table_exists(conn, table):
            return 0
        return int(conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params).fetchone()["n"])

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as conn:
            return {
                "unresolved": self._count(conn, "conversation_observability", "outcome='UNRESOLVED'"),
                "runtime_errors": self._count(conn, "conversation_observability", "outcome='ERROR'"),
                "failed_deliveries": self._count(conn, "delivery_statuses", "lower(status) IN ('failed','error','undelivered')"),
                "kyc_submitted": self._count(conn, "driver_kyc_profiles", "status='SUBMITTED'"),
                "kyc_rejected": self._count(conn, "driver_kyc_profiles", "status='REJECTED'"),
                "open_rfqs": self._count(conn, "universal_rfqs", "status='OPEN'"),
                "open_rides": self._count(conn, "rides", "status IN ('OPEN','FULL')"),
                "accepted_ride_bookings": self._count(conn, "ride_bookings", "status='ACCEPTED'"),
            }

    def unresolved(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if not self._table_exists(conn, "conversation_observability"):
                return []
            rows = conn.execute("""SELECT id,sender_user_id,message_preview,detected_domain,outcome,error_type,created_at
                                   FROM conversation_observability
                                   WHERE outcome IN ('UNRESOLVED','ERROR') ORDER BY id DESC LIMIT ?""",
                                (max(1, min(int(limit), 50)),)).fetchall()
            return [dict(x) for x in rows]

    def failed_deliveries(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if not self._table_exists(conn, "delivery_statuses"):
                return []
            rows = conn.execute("""SELECT * FROM delivery_statuses
                                   WHERE lower(status) IN ('failed','error','undelivered')
                                   ORDER BY rowid DESC LIMIT ?""", (max(1, min(int(limit), 50)),)).fetchall()
            return [dict(x) for x in rows]

    def pending_kyc(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if not self._table_exists(conn, "driver_kyc_profiles"):
                return []
            rows = conn.execute("""SELECT driver_user_id,status,submitted_at,rejection_reason,updated_at
                                   FROM driver_kyc_profiles WHERE status IN ('SUBMITTED','REJECTED')
                                   ORDER BY updated_at DESC LIMIT ?""", (max(1, min(int(limit), 50)),)).fetchall()
            return [dict(x) for x in rows]

    def open_rfqs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if not self._table_exists(conn, "universal_rfqs"):
                return []
            rows = conn.execute("""SELECT id,requester_user_id,rfq_type,title,status,created_at
                                   FROM universal_rfqs WHERE status='OPEN' ORDER BY id DESC LIMIT ?""",
                                (max(1, min(int(limit), 50)),)).fetchall()
            return [dict(x) for x in rows]
