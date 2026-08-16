"""Persistence for unified conversation routing, unresolved requests and runtime failures."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


class ConversationObservabilityRepository:
    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_observability (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_user_id TEXT NOT NULL,
                    message_preview TEXT,
                    detected_domain TEXT NOT NULL DEFAULT 'UNKNOWN',
                    route_source TEXT,
                    outcome TEXT NOT NULL,
                    error_type TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conv_obs_outcome
                    ON conversation_observability(outcome, created_at);
                CREATE INDEX IF NOT EXISTS idx_conv_obs_domain
                    ON conversation_observability(detected_domain, created_at);
                """
            )

    def record(
        self,
        sender_user_id: str,
        message: str,
        detected_domain: str,
        outcome: str,
        route_source: str | None = None,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = self._now()
        preview = " ".join(str(message or "").strip().split())[:240]
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO conversation_observability(
                       sender_user_id,message_preview,detected_domain,route_source,outcome,error_type,metadata_json,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    str(sender_user_id), preview, str(detected_domain or "UNKNOWN").upper(),
                    route_source, str(outcome or "UNKNOWN").upper(), error_type,
                    json.dumps(metadata or {}, ensure_ascii=False), now,
                ),
            )
            return int(cur.lastrowid)

    def unresolved(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM conversation_observability
                   WHERE outcome IN ('UNRESOLVED','ERROR')
                   ORDER BY id DESC LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM conversation_observability").fetchone()["n"]
            unresolved = conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_observability WHERE outcome='UNRESOLVED'"
            ).fetchone()["n"]
            errors = conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_observability WHERE outcome='ERROR'"
            ).fetchone()["n"]
        return {"total": int(total), "unresolved": int(unresolved), "errors": int(errors)}
