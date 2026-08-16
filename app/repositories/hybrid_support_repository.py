"""Persistent unresolved-question tickets for PODX hybrid support."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class HybridSupportRepository:
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
                CREATE TABLE IF NOT EXISTS hybrid_support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requester_user_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    answer TEXT,
                    answered_by TEXT,
                    knowledge_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_hybrid_support_status ON hybrid_support_tickets(status, id);
                CREATE INDEX IF NOT EXISTS idx_hybrid_support_requester ON hybrid_support_tickets(requester_user_id, id);
                """
            )

    @staticmethod
    def question_key(question: str) -> str:
        normalized = " ".join(str(question or "").casefold().strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]

    def create_once(self, requester_user_id: str, question: str) -> Dict[str, Any]:
        key = self.question_key(question)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hybrid_support_tickets WHERE requester_user_id=? AND question_key=? AND status='PENDING' ORDER BY id DESC LIMIT 1",
                (str(requester_user_id), key),
            ).fetchone()
            if row:
                data = dict(row); data["created"] = False; return data
            now = self._now()
            cur = conn.execute(
                "INSERT INTO hybrid_support_tickets(requester_user_id,question,question_key,status,created_at,updated_at) VALUES(?,?,?,'PENDING',?,?)",
                (str(requester_user_id), str(question).strip(), key, now, now),
            )
            row = conn.execute("SELECT * FROM hybrid_support_tickets WHERE id=?", (int(cur.lastrowid),)).fetchone()
        data = dict(row); data["created"] = True; return data

    def get(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM hybrid_support_tickets WHERE id=?", (int(ticket_id),)).fetchone()
        return dict(row) if row else None

    def answer(self, ticket_id: int, answer: str, answered_by: str, knowledge_id: int | None = None) -> Optional[Dict[str, Any]]:
        text = " ".join(str(answer or "").strip().split())
        if not text:
            return None
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE hybrid_support_tickets SET status='ANSWERED',answer=?,answered_by=?,knowledge_id=?,updated_at=? WHERE id=? AND status='PENDING'",
                (text, str(answered_by), knowledge_id, now, int(ticket_id)),
            )
            if cur.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM hybrid_support_tickets WHERE id=?", (int(ticket_id),)).fetchone()
        return dict(row) if row else None
