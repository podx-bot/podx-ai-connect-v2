import json
from typing import Any

from app.database.database import Database
from app.models.session import ConversationSession, ConversationStep


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, sender_mobile: str) -> ConversationSession:
        row = self.database.fetchone(
            """
            SELECT step, data_json
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
