"""Persistent owner-scoped business ledger entries and balances."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class BusinessLedgerRepository:
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
                CREATE TABLE IF NOT EXISTS business_ledger_entries(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id TEXT NOT NULL,
                    counterparty TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    note TEXT,
                    reference TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_business_ledger_owner_party
                    ON business_ledger_entries(owner_user_id, counterparty, id);
                CREATE INDEX IF NOT EXISTS idx_business_ledger_owner_created
                    ON business_ledger_entries(owner_user_id, id);
                """
            )

    def add_entry(self, owner_user_id: str, counterparty: str, entry_type: str,
                  amount: float, note: str | None = None, reference: str | None = None) -> int:
        kind = str(entry_type or "").upper().strip()
        if kind not in {"RECEIVABLE", "PAYABLE", "RECEIVED", "PAID", "ADJUSTMENT_PLUS", "ADJUSTMENT_MINUS"}:
            raise ValueError("unsupported ledger entry type")
        value = round(float(amount), 2)
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        party = " ".join(str(counterparty or "").strip().split())
        if not party:
            raise ValueError("counterparty is required")
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO business_ledger_entries(
                    owner_user_id,counterparty,entry_type,amount,note,reference,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (str(owner_user_id), party, kind, value, note, reference, self._now()),
            )
            return int(cur.lastrowid)

    def balance(self, owner_user_id: str, counterparty: str | None = None) -> float:
        params: list[object] = [str(owner_user_id)]
        where = "owner_user_id=?"
        if counterparty is not None:
            where += " AND lower(counterparty)=lower(?)"
            params.append(" ".join(str(counterparty).strip().split()))
        sql = f"""
            SELECT COALESCE(SUM(CASE
                WHEN entry_type IN ('RECEIVABLE','ADJUSTMENT_PLUS') THEN amount
                WHEN entry_type IN ('RECEIVED','ADJUSTMENT_MINUS') THEN -amount
                WHEN entry_type='PAYABLE' THEN -amount
                WHEN entry_type='PAID' THEN amount
                ELSE 0 END),0) AS balance
            FROM business_ledger_entries WHERE {where}
        """
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return round(float(row["balance"] if row else 0.0), 2)

    def statement(self, owner_user_id: str, counterparty: str | None = None, limit: int = 10) -> list[dict]:
        params: list[object] = [str(owner_user_id)]
        where = "owner_user_id=?"
        if counterparty is not None:
            where += " AND lower(counterparty)=lower(?)"
            params.append(" ".join(str(counterparty).strip().split()))
        params.append(max(1, min(int(limit), 50)))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM business_ledger_entries WHERE {where} ORDER BY id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def parties(self, owner_user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT counterparty,
                    SUM(CASE
                        WHEN entry_type IN ('RECEIVABLE','ADJUSTMENT_PLUS') THEN amount
                        WHEN entry_type IN ('RECEIVED','ADJUSTMENT_MINUS') THEN -amount
                        WHEN entry_type='PAYABLE' THEN -amount
                        WHEN entry_type='PAID' THEN amount
                        ELSE 0 END) AS balance
                   FROM business_ledger_entries
                   WHERE owner_user_id=?
                   GROUP BY lower(counterparty)
                   ORDER BY MAX(id) DESC LIMIT ?""",
                (str(owner_user_id), max(1, min(int(limit), 50))),
            ).fetchall()
        return [{"counterparty": str(row["counterparty"]), "balance": round(float(row["balance"] or 0), 2)} for row in rows]
