"""Persistent dedupe ledger for recurring demand opportunity notifications."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class DemandSignalRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS demand_intelligence_signals (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       signal_key TEXT NOT NULL UNIQUE,
                       domain TEXT NOT NULL,
                       subject TEXT NOT NULL,
                       area TEXT,
                       demand_count INTEGER NOT NULL,
                       created_at TEXT NOT NULL
                   )"""
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def claim(self, signal_key: str, domain: str, subject: str, area: str, demand_count: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO demand_intelligence_signals(
                       signal_key,domain,subject,area,demand_count,created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (str(signal_key), str(domain), str(subject), str(area or ""), int(demand_count), now),
            )
            return int(cur.rowcount or 0) == 1

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM demand_intelligence_signals").fetchone()
        return int(row["n"] if row else 0)
