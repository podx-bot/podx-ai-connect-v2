from typing import Optional

from app.database.database import Database


class DeliveryLogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_status(
        self,
        provider_message_id: str,
        recipient_mobile: Optional[str],
        status: str,
        error_message: Optional[str]
    ) -> None:
        self.database.execute(
            """
            INSERT INTO delivery_statuses (
                provider_message_id,
                recipient_mobile,
                status,
                error_message
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                provider_message_id,
                recipient_mobile,
                status,
                error_message
            )
        )

    def latest_for_message(self, provider_message_id: str) -> Optional[dict]:
        row = self.database.fetchone(
            """
            SELECT * FROM delivery_statuses
            WHERE provider_message_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (provider_message_id,),
        )
        return dict(row) if row is not None else None

    def failed_recent(self, limit: int = 50) -> list[dict]:
        rows = self.database.fetchall(
            """
            SELECT d.*
            FROM delivery_statuses d
            JOIN (
                SELECT provider_message_id, MAX(id) AS max_id
                FROM delivery_statuses
                GROUP BY provider_message_id
            ) latest ON latest.max_id = d.id
            WHERE LOWER(d.status) IN ('failed', 'undelivered', 'error')
               OR COALESCE(d.error_message, '') <> ''
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )
        return [dict(row) for row in rows]
