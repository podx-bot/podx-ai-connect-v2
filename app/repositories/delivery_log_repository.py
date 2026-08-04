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
