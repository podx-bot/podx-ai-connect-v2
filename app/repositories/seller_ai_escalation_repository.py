"""Persistence for ask-seller-once product knowledge escalation."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class SellerAIEscalationRepository:
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
                CREATE TABLE IF NOT EXISTS seller_ai_escalations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    seller_user_id TEXT NOT NULL,
                    buyer_user_id TEXT NOT NULL,
                    question_key TEXT NOT NULL,
                    question TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    answer TEXT,
                    created_at TEXT NOT NULL,
                    answered_at TEXT,
                    UNIQUE(product_id, seller_user_id, question_key, status)
                );
                CREATE INDEX IF NOT EXISTS idx_seller_ai_pending
                ON seller_ai_escalations(seller_user_id, status, id);
            """)

    def create_once(self, product_id: int, seller_user_id: str, buyer_user_id: str, question_key: str, question: str) -> Dict[str, Any]:
        key = " ".join(str(question_key or "general").casefold().split())
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM seller_ai_escalations WHERE product_id=? AND seller_user_id=? AND question_key=? AND status='PENDING' ORDER BY id DESC LIMIT 1",
                (int(product_id), str(seller_user_id), key),
            ).fetchone()
            if row:
                return {**dict(row), "created": False}
            cur = conn.execute(
                "INSERT INTO seller_ai_escalations(product_id,seller_user_id,buyer_user_id,question_key,question,status,created_at) VALUES(?,?,?,?,?,'PENDING',?)",
                (int(product_id), str(seller_user_id), str(buyer_user_id), key, str(question).strip(), self._now()),
            )
            row = conn.execute("SELECT * FROM seller_ai_escalations WHERE id=?", (int(cur.lastrowid),)).fetchone()
            return {**dict(row), "created": True}

    def latest_pending_for_seller(self, seller_user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM seller_ai_escalations WHERE seller_user_id=? AND status='PENDING' ORDER BY id DESC LIMIT 1",
                (str(seller_user_id),),
            ).fetchone()
        return dict(row) if row else None

    def answer(self, escalation_id: int, answer: str) -> Optional[Dict[str, Any]]:
        clean = str(answer or "").strip()
        if not clean:
            return None
        with self._connect() as conn:
            conn.execute(
                "UPDATE seller_ai_escalations SET status='ANSWERED',answer=?,answered_at=? WHERE id=? AND status='PENDING'",
                (clean, self._now(), int(escalation_id)),
            )
            row = conn.execute("SELECT * FROM seller_ai_escalations WHERE id=?", (int(escalation_id),)).fetchone()
        return dict(row) if row and row["status"] == "ANSWERED" else None
