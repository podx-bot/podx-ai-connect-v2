from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Any


class DriverKYCRepository:
    REQUIRED_DOCS = ("DL", "VEHICLE", "INSURANCE", "VEHICLE_PHOTO")

    def __init__(self, db_path: str) -> None:
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
                CREATE TABLE IF NOT EXISTS driver_kyc_profiles(
                    driver_user_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'DRAFT',
                    submitted_at TEXT,
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS driver_kyc_documents(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    driver_user_id TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    document_number TEXT,
                    vehicle_details TEXT,
                    expiry_date TEXT,
                    media_ref TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    reviewed_at TEXT,
                    reviewed_by TEXT,
                    rejection_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(driver_user_id, doc_type)
                );
                CREATE INDEX IF NOT EXISTS idx_driver_kyc_docs_driver ON driver_kyc_documents(driver_user_id, doc_type);
                """
            )

    def start(self, driver_user_id: str) -> dict[str, Any]:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO driver_kyc_profiles(driver_user_id,status,created_at,updated_at)
                   VALUES(?, 'DRAFT', ?, ?)
                   ON CONFLICT(driver_user_id) DO UPDATE SET updated_at=excluded.updated_at""",
                (str(driver_user_id), now, now),
            )
        return self.status(driver_user_id)

    def save_document(self, driver_user_id: str, doc_type: str, document_number: str | None = None,
                      expiry_date: str | None = None, media_ref: str | None = None,
                      vehicle_details: str | None = None) -> dict[str, Any]:
        doc_type = str(doc_type).upper().strip()
        if doc_type not in self.REQUIRED_DOCS:
            raise ValueError("Unsupported KYC document type")
        self.start(driver_user_id)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO driver_kyc_documents(driver_user_id,doc_type,document_number,vehicle_details,expiry_date,media_ref,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'PENDING',?,?)
                   ON CONFLICT(driver_user_id,doc_type) DO UPDATE SET
                     document_number=excluded.document_number,vehicle_details=excluded.vehicle_details,
                     expiry_date=excluded.expiry_date,media_ref=excluded.media_ref,status='PENDING',
                     reviewed_at=NULL,reviewed_by=NULL,rejection_reason=NULL,updated_at=excluded.updated_at""",
                (str(driver_user_id), doc_type, document_number, vehicle_details, expiry_date, media_ref, now, now),
            )
            conn.execute("UPDATE driver_kyc_profiles SET status='DRAFT',reviewed_at=NULL,reviewed_by=NULL,rejection_reason=NULL,updated_at=? WHERE driver_user_id=?", (now, str(driver_user_id)))
        return self.status(driver_user_id)

    def submit(self, driver_user_id: str) -> dict[str, Any]:
        state = self.status(driver_user_id)
        missing = state["missing"]
        if missing:
            return {**state, "result": "MISSING"}
        now = self._now()
        with self._connect() as conn:
            conn.execute("UPDATE driver_kyc_profiles SET status='SUBMITTED',submitted_at=?,updated_at=? WHERE driver_user_id=?", (now, now, str(driver_user_id)))
        return {**self.status(driver_user_id), "result": "SUBMITTED"}

    def review_profile(self, driver_user_id: str, reviewer: str, approve: bool, reason: str | None = None) -> dict[str, Any]:
        now = self._now(); status = "APPROVED" if approve else "REJECTED"
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM driver_kyc_profiles WHERE driver_user_id=?", (str(driver_user_id),)).fetchone()
            if not row:
                return {"result": "NOT_FOUND"}
            conn.execute("UPDATE driver_kyc_profiles SET status=?,reviewed_at=?,reviewed_by=?,rejection_reason=?,updated_at=? WHERE driver_user_id=?", (status, now, str(reviewer), None if approve else (reason or "Review failed"), now, str(driver_user_id)))
            if approve:
                conn.execute("UPDATE driver_kyc_documents SET status='APPROVED',reviewed_at=?,reviewed_by=?,rejection_reason=NULL,updated_at=? WHERE driver_user_id=?", (now, str(reviewer), now, str(driver_user_id)))
        return {**self.status(driver_user_id), "result": status}

    def list_expiring(self, days: int = 30) -> list[dict[str, Any]]:
        today = date.today()
        out: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM driver_kyc_documents WHERE expiry_date IS NOT NULL AND status='APPROVED'").fetchall()
        for row in rows:
            try:
                expiry = date.fromisoformat(str(row["expiry_date"]))
            except ValueError:
                continue
            remaining = (expiry - today).days
            if remaining <= int(days):
                out.append({**dict(row), "days_remaining": remaining, "expired": remaining < 0})
        out.sort(key=lambda x: x["days_remaining"])
        return out

    def status(self, driver_user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            profile = conn.execute("SELECT * FROM driver_kyc_profiles WHERE driver_user_id=?", (str(driver_user_id),)).fetchone()
            docs = conn.execute("SELECT * FROM driver_kyc_documents WHERE driver_user_id=? ORDER BY doc_type", (str(driver_user_id),)).fetchall()
        docs_list = [dict(x) for x in docs]
        present = {str(x["doc_type"]).upper() for x in docs_list}
        missing = [x for x in self.REQUIRED_DOCS if x not in present]
        expired = []
        for doc in docs_list:
            expiry = doc.get("expiry_date")
            if not expiry:
                continue
            try:
                if date.fromisoformat(str(expiry)) < date.today():
                    expired.append(str(doc["doc_type"]))
            except ValueError:
                expired.append(str(doc["doc_type"]))
        return {
            "driver_user_id": str(driver_user_id),
            "status": str(profile["status"]) if profile else "NOT_STARTED",
            "profile": dict(profile) if profile else None,
            "documents": docs_list,
            "missing": missing,
            "expired": expired,
            "eligible": bool(profile and str(profile["status"]) == "APPROVED" and not expired),
        }
