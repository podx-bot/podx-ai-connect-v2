"""Persistence for shareable PODX business desks and owner-learning questions."""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class BusinessCustomerDeskRepository:
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
                CREATE TABLE IF NOT EXISTS business_customer_desks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_mobile TEXT NOT NULL UNIQUE,
                    business_code TEXT NOT NULL UNIQUE,
                    business_name TEXT NOT NULL,
                    category TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS business_customer_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_code TEXT NOT NULL,
                    owner_mobile TEXT NOT NULL,
                    customer_mobile TEXT NOT NULL,
                    question TEXT NOT NULL,
                    normalized_question TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    answer TEXT,
                    created_at TEXT NOT NULL,
                    answered_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_business_desk_code ON business_customer_desks(business_code,status);
                CREATE INDEX IF NOT EXISTS idx_business_question_owner ON business_customer_questions(owner_mobile,status,id);
                CREATE INDEX IF NOT EXISTS idx_business_question_dedupe ON business_customer_questions(business_code,customer_mobile,normalized_question,status);
                """
            )

    def enable(self, owner_mobile: str, business_name: str, category: str | None = None) -> dict:
        existing = self.find_by_owner(owner_mobile)
        code = existing["business_code"] if existing else self._new_code(business_name)
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO business_customer_desks(owner_mobile,business_code,business_name,category,status,created_at,updated_at)
                   VALUES(?,?,?,?, 'ACTIVE', ?, ?)
                   ON CONFLICT(owner_mobile) DO UPDATE SET
                     business_name=excluded.business_name,
                     category=excluded.category,
                     status='ACTIVE',
                     updated_at=excluded.updated_at""",
                (str(owner_mobile), code, business_name.strip(), (category or "").strip() or None, now, now),
            )
        return self.find_by_owner(owner_mobile) or {}

    def disable(self, owner_mobile: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE business_customer_desks SET status='DISABLED', updated_at=? WHERE owner_mobile=?",
                (self._now(), str(owner_mobile)),
            )
        return cur.rowcount > 0

    def find_by_owner(self, owner_mobile: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM business_customer_desks WHERE owner_mobile=?", (str(owner_mobile),)).fetchone()
        return dict(row) if row else None

    def find_by_code(self, business_code: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM business_customer_desks WHERE upper(business_code)=upper(?) AND status='ACTIVE'",
                (str(business_code).strip(),),
            ).fetchone()
        return dict(row) if row else None

    def create_or_get_pending(self, desk: dict, customer_mobile: str, question: str) -> tuple[dict, bool]:
        normalized = self._normalize(question)
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM business_customer_questions
                   WHERE business_code=? AND customer_mobile=? AND normalized_question=? AND status='PENDING'
                   ORDER BY id DESC LIMIT 1""",
                (desk["business_code"], str(customer_mobile), normalized),
            ).fetchone()
            if row:
                return dict(row), False
            now = self._now()
            cur = conn.execute(
                """INSERT INTO business_customer_questions(
                       business_code,owner_mobile,customer_mobile,question,normalized_question,status,created_at)
                   VALUES(?,?,?,?,?,'PENDING',?)""",
                (desk["business_code"], desk["owner_mobile"], str(customer_mobile), question.strip(), normalized, now),
            )
            qid = int(cur.lastrowid)
            row = conn.execute("SELECT * FROM business_customer_questions WHERE id=?", (qid,)).fetchone()
        return dict(row), True

    def pending_for_owner(self, owner_mobile: str, question_id: int) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM business_customer_questions WHERE id=? AND owner_mobile=? AND status='PENDING'",
                (int(question_id), str(owner_mobile)),
            ).fetchone()
        return dict(row) if row else None

    def answer(self, owner_mobile: str, question_id: int, answer: str) -> Optional[dict]:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE business_customer_questions
                   SET status='ANSWERED', answer=?, answered_at=?
                   WHERE id=? AND owner_mobile=? AND status='PENDING'""",
                (answer.strip(), now, int(question_id), str(owner_mobile)),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute("SELECT * FROM business_customer_questions WHERE id=?", (int(question_id),)).fetchone()
        return dict(row) if row else None

    def latest_pending_for_owner(self, owner_mobile: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM business_customer_questions WHERE owner_mobile=? AND status='PENDING' ORDER BY id DESC LIMIT 1",
                (str(owner_mobile),),
            ).fetchone()
        return dict(row) if row else None

    def _new_code(self, business_name: str) -> str:
        prefix = re.sub(r"[^A-Za-z0-9]", "", business_name.upper())[:5] or "BIZ"
        for _ in range(20):
            code = f"{prefix}{secrets.randbelow(900)+100}"
            if not self.find_by_code(code):
                return code
        return f"BIZ{secrets.token_hex(3).upper()}"

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").casefold().strip().split())
