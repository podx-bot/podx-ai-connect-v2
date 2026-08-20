"""Persistent turn ledger for PODX Conversation OS.

Stores the compact channel-neutral conversation state plus an append-only turn
history. This allows WhatsApp, app and web adapters to resume the same active
conversation without reconstructing meaning from the latest message alone.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ConversationTurnLedgerRepository:
    STATE_TABLE = "conversation_os_state"
    TURN_TABLE = "conversation_os_turns"

    def __init__(self, db_path: str = "podx.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.STATE_TABLE} (
                    user_id TEXT PRIMARY KEY,
                    channel TEXT,
                    goal TEXT,
                    active_flow TEXT,
                    active_entity TEXT,
                    known_fields_json TEXT NOT NULL DEFAULT '{{}}',
                    missing_fields_json TEXT NOT NULL DEFAULT '[]',
                    pending_action TEXT,
                    last_bot_message TEXT,
                    last_bot_intent TEXT,
                    expected_reply_type TEXT,
                    last_user_message TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TURN_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    channel TEXT,
                    user_message TEXT,
                    bot_message TEXT,
                    turn_kind TEXT,
                    resolved_meaning TEXT,
                    next_action TEXT,
                    confidence REAL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_conversation_turn_user ON {self.TURN_TABLE}(user_id, id DESC)"
            )

    def load_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.STATE_TABLE} WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["known_fields"] = json.loads(data.pop("known_fields_json") or "{}")
        data["missing_fields"] = json.loads(data.pop("missing_fields_json") or "[]")
        return data

    def save_state(self, user_id: str, state: Dict[str, Any], channel: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.STATE_TABLE} (
                    user_id, channel, goal, active_flow, active_entity,
                    known_fields_json, missing_fields_json, pending_action,
                    last_bot_message, last_bot_intent, expected_reply_type,
                    last_user_message, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    channel = excluded.channel,
                    goal = excluded.goal,
                    active_flow = excluded.active_flow,
                    active_entity = excluded.active_entity,
                    known_fields_json = excluded.known_fields_json,
                    missing_fields_json = excluded.missing_fields_json,
                    pending_action = excluded.pending_action,
                    last_bot_message = excluded.last_bot_message,
                    last_bot_intent = excluded.last_bot_intent,
                    expected_reply_type = excluded.expected_reply_type,
                    last_user_message = excluded.last_user_message,
                    updated_at = excluded.updated_at
                """,
                (
                    str(user_id), channel, state.get("goal"), state.get("active_flow"),
                    state.get("active_entity"),
                    json.dumps(state.get("known_fields") or {}, ensure_ascii=False),
                    json.dumps(state.get("missing_fields") or [], ensure_ascii=False),
                    state.get("pending_action"), state.get("last_bot_message"),
                    state.get("last_bot_intent"), state.get("expected_reply_type"),
                    state.get("last_user_message"), now,
                ),
            )

    def append_turn(
        self,
        user_id: str,
        *,
        channel: str | None,
        user_message: str | None,
        bot_message: str | None,
        turn_kind: str | None,
        resolved_meaning: str | None,
        next_action: str | None,
        confidence: float | None,
        state: Dict[str, Any],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                f"""
                INSERT INTO {self.TURN_TABLE} (
                    user_id, channel, user_message, bot_message, turn_kind,
                    resolved_meaning, next_action, confidence, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user_id), channel, user_message, bot_message, turn_kind,
                    resolved_meaning, next_action, confidence,
                    json.dumps(state, ensure_ascii=False), now,
                ),
            )
            return int(cur.lastrowid)

    def recent_turns(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self.TURN_TABLE}
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (str(user_id), max(1, int(limit))),
            ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["state"] = json.loads(data.pop("state_json") or "{}")
            result.append(data)
        return result
