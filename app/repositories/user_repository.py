from typing import Optional

from app.database.database import Database


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def find_by_whatsapp_mobile(
        self,
        whatsapp_mobile: str
    ) -> Optional[dict]:
        row = self.database.fetchone(
            """
            SELECT *
            FROM users
            WHERE whatsapp_mobile = ?
            """,
            (whatsapp_mobile,)
        )
        return dict(row) if row else None

    def create_or_update_registration(
        self,
        whatsapp_mobile: str,
        entered_mobile: str,
        name: str,
        language: str,
        area: str
    ) -> None:
        self.database.execute(
            """
            INSERT INTO users (
                whatsapp_mobile,
                entered_mobile,
                name,
                language,
                area,
                registration_complete,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile)
            DO UPDATE SET
                entered_mobile = excluded.entered_mobile,
                name = excluded.name,
                language = excluded.language,
                area = excluded.area,
                registration_complete = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                whatsapp_mobile,
                entered_mobile,
                name,
                language,
                area
            )
        )

    def save_location(
        self,
        whatsapp_mobile: str,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        location_address: Optional[str] = None
    ) -> None:
        self.database.execute(
            """
            INSERT INTO users (
                whatsapp_mobile,
                latitude,
                longitude,
                location_name,
                location_address,
                location_updated_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile)
            DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                location_name = excluded.location_name,
                location_address = excluded.location_address,
                location_updated_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                whatsapp_mobile,
                latitude,
                longitude,
                location_name,
                location_address
            )
        )
