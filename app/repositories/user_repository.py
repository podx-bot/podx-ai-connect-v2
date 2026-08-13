import re
from typing import Optional

from app.database.database import Database
from app.repositories.capability_repository import CapabilityRepository


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.capability_repository = CapabilityRepository(database)

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
        if not row:
            return None
        user = dict(row)
        user["capabilities"] = self.list_capabilities(whatsapp_mobile)
        return user

    def add_capability(
        self,
        whatsapp_mobile: str,
        capability: str,
        source: str | None = "conversation",
    ) -> None:
        self.capability_repository.add(
            whatsapp_mobile,
            capability,
            source=source,
        )

    def add_capabilities(
        self,
        whatsapp_mobile: str,
        capabilities,
        source: str | None = "registration",
    ) -> None:
        self.capability_repository.add_many(
            whatsapp_mobile,
            capabilities,
            source=source,
        )

    def list_capabilities(self, whatsapp_mobile: str) -> list[str]:
        return self.capability_repository.list_for_user(whatsapp_mobile)

    def has_capability(self, whatsapp_mobile: str, capability: str) -> bool:
        return self.capability_repository.has(whatsapp_mobile, capability)

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

    def save_worker_profile(
        self,
        whatsapp_mobile: str,
        category: str,
        experience: str,
        availability: str
    ) -> None:
        self.database.execute(
            """
            INSERT INTO users (
                whatsapp_mobile,
                role,
                job_category,
                experience,
                availability,
                worker_registration_complete,
                updated_at
            )
            VALUES (?, 'WORKER', ?, ?, ?, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile)
            DO UPDATE SET
                role = 'WORKER',
                job_category = excluded.job_category,
                experience = excluded.experience,
                availability = excluded.availability,
                worker_registration_complete = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                whatsapp_mobile,
                category,
                experience,
                availability
            )
        )
        self.add_capability(whatsapp_mobile, "WORKER", source="job_flow")

    def complete_worker_registration(
        self,
        whatsapp_mobile: str
    ) -> None:
        self.database.execute(
            """
            UPDATE users
            SET worker_registration_complete = 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE whatsapp_mobile = ?
            """,
            (whatsapp_mobile,)
        )
        self.add_capability(whatsapp_mobile, "WORKER", source="job_flow")

    def save_employer_post(
        self,
        whatsapp_mobile: str,
        service: str,
        requirement: str
    ) -> int:
        self.database.execute(
            """
            UPDATE employer_jobs
            SET status = 'CANCELLED',
                updated_at = CURRENT_TIMESTAMP
            WHERE employer_mobile = ?
              AND status = 'DRAFT'
            """,
            (whatsapp_mobile,)
        )

        employer = self.find_by_whatsapp_mobile(whatsapp_mobile) or {}
        employer_contact = employer.get("entered_mobile") or whatsapp_mobile
        required_workers = self._required_worker_count(requirement)

        cursor = self.database.execute(
            """
            INSERT INTO employer_jobs (
                employer_mobile,
                service,
                requirement,
                required_workers,
                employer_contact,
                status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'DRAFT', CURRENT_TIMESTAMP)
            """,
            (
                whatsapp_mobile,
                service,
                requirement,
                required_workers,
                employer_contact
            )
        )
        self.add_capability(whatsapp_mobile, "EMPLOYER", source="job_flow")
        return int(cursor.lastrowid)

    def save_employer_job_location(
        self,
        whatsapp_mobile: str,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        location_address: Optional[str] = None
    ) -> Optional[dict]:
        row = self.database.fetchone(
            """
            SELECT *
            FROM employer_jobs
            WHERE employer_mobile = ?
              AND status = 'DRAFT'
            ORDER BY id DESC
            LIMIT 1
            """,
            (whatsapp_mobile,)
        )
        if not row:
            return None

        job_id = int(row["id"])
        self.database.execute(
            """
            UPDATE employer_jobs
            SET latitude = ?,
                longitude = ?,
                location_name = ?,
                location_address = ?,
                status = 'OPEN',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                latitude,
                longitude,
                location_name,
                location_address,
                job_id
            )
        )
        return self.find_employer_job(job_id)

    def find_employer_job(self, job_id: int) -> Optional[dict]:
        row = self.database.fetchone(
            "SELECT * FROM employer_jobs WHERE id = ?",
            (job_id,)
        )
        return dict(row) if row else None

    def find_candidate_workers(self, category: str) -> list[dict]:
        rows = self.database.fetchall(
            """
            SELECT *
            FROM users
            WHERE worker_registration_complete = 1
              AND job_category = ?
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND availability IS NOT NULL
            ORDER BY updated_at DESC
            """,
            (category,)
        )
        return [dict(row) for row in rows]

    def has_match_notification(
        self,
        employer_job_id: int,
        worker_mobile: str
    ) -> bool:
        row = self.database.fetchone(
            """
            SELECT 1
            FROM match_notifications
            WHERE employer_job_id = ?
              AND worker_mobile = ?
            LIMIT 1
            """,
            (employer_job_id, worker_mobile)
        )
        return row is not None

    def record_match_notification(
        self,
        employer_job_id: int,
        worker_mobile: str,
        distance_km: float,
        provider_message_id: Optional[str]
    ) -> None:
        self.database.execute(
            """
            INSERT OR IGNORE INTO match_notifications (
                employer_job_id,
                worker_mobile,
                distance_km,
                provider_message_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                employer_job_id,
                worker_mobile,
                distance_km,
                provider_message_id
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

    @staticmethod
    def _required_worker_count(requirement: str) -> int:
        matches = re.findall(r"\b(\d{1,3})\b", str(requirement))
        for value in matches:
            count = int(value)
            if 1 <= count <= 500:
                return count
        return 1
