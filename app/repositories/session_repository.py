import json
from datetime import datetime, timezone
from typing import Any

from app.database.database import Database
from app.models.session import ConversationSession, ConversationStep


class SessionRepository:
    STALE_AFTER_SECONDS = 24 * 60 * 60
    STABLE_STEPS = {ConversationStep.START, ConversationStep.MAIN_MENU}

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _is_stale(updated_at: str | None) -> bool:
        if not updated_at:
            return False
        try:
            value = str(updated_at).replace("Z", "+00:00")
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() > SessionRepository.STALE_AFTER_SECONDS
        except (TypeError, ValueError):
            return False

    def get(self, sender_mobile: str) -> ConversationSession:
        row = self.database.fetchone(
            """
            SELECT step, data_json, updated_at
            FROM conversation_sessions
            WHERE sender_mobile = ?
            """,
            (sender_mobile,)
        )

        if row is None:
            session = ConversationSession()
            self.save(sender_mobile, session)
            return session

        try:
            step = ConversationStep(row["step"])
        except (ValueError, TypeError):
            step = ConversationStep.START

        try:
            data: dict[str, Any] = json.loads(row["data_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}

        # A user should never remain trapped forever in a half-finished flow.
        # Preserve stable menu states, but reset old intermediate states after 24h.
        if step not in self.STABLE_STEPS and self._is_stale(row["updated_at"]):
            session = ConversationSession(step=ConversationStep.MAIN_MENU, data={})
            self.save(sender_mobile, session)
            return session

        return ConversationSession(step=step, data=data)

    def save(
        self,
        sender_mobile: str,
        session: ConversationSession
    ) -> None:
        self.database.execute(
            """
            INSERT INTO conversation_sessions (
                sender_mobile,
                step,
                data_json,
                updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(sender_mobile) DO UPDATE SET
                step = excluded.step,
                data_json = excluded.data_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                sender_mobile,
                session.step.value,
                json.dumps(session.data, ensure_ascii=False)
            )
        )

    def reset(self, sender_mobile: str) -> ConversationSession:
        session = ConversationSession()
        self.save(sender_mobile, session)
        return session
