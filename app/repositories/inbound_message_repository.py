from app.database.database import Database


class InboundMessageRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def exists(self, provider_message_id: str) -> bool:
        row = self.database.fetchone(
            """
            SELECT 1
            FROM inbound_messages
            WHERE provider_message_id = ?
            """,
            (provider_message_id,)
        )
        return row is not None

    def save(
        self,
        provider_message_id: str,
        sender_mobile: str,
        message_text: str
    ) -> None:
        self.database.execute(
            """
            INSERT OR IGNORE INTO inbound_messages (
                provider_message_id,
                sender_mobile,
                message_text
            )
            VALUES (?, ?, ?)
            """,
            (
                provider_message_id,
                sender_mobile,
                message_text
            )
        )
