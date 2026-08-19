from __future__ import annotations

from typing import Optional

from app.database.database import Database


class FaceWelcomeRepository:
    """Consent-first persistence for Face Welcome enrollment metadata.

    Raw face images are deliberately not stored here. The repository keeps only
    enrollment state plus a non-reversible SHA-256 digest of the accepted photo
    payload. A future biometric provider can attach its own template/reference
    without changing the consent contract.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS face_welcome_enrollments (
                whatsapp_mobile TEXT PRIMARY KEY,
                consent_status TEXT NOT NULL DEFAULT 'NOT_ASKED',
                photo_sha256 TEXT,
                biometric_template_ref TEXT,
                enabled INTEGER NOT NULL DEFAULT 0,
                consented_at TEXT,
                enrolled_at TEXT,
                revoked_at TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def get(self, whatsapp_mobile: str) -> Optional[dict]:
        row = self.database.fetchone(
            "SELECT * FROM face_welcome_enrollments WHERE whatsapp_mobile=?",
            (whatsapp_mobile,),
        )
        return dict(row) if row else None

    def mark_consent(self, whatsapp_mobile: str, accepted: bool) -> None:
        status = "ACCEPTED" if accepted else "DECLINED"
        enabled = 1 if accepted else 0
        self.database.execute(
            """
            INSERT INTO face_welcome_enrollments (
                whatsapp_mobile, consent_status, enabled, consented_at, updated_at
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile) DO UPDATE SET
                consent_status=excluded.consent_status,
                enabled=excluded.enabled,
                consented_at=CURRENT_TIMESTAMP,
                revoked_at=CASE WHEN excluded.enabled=0 THEN CURRENT_TIMESTAMP ELSE NULL END,
                updated_at=CURRENT_TIMESTAMP
            """,
            (whatsapp_mobile, status, enabled),
        )

    def save_photo_digest(self, whatsapp_mobile: str, photo_sha256: str) -> None:
        self.database.execute(
            """
            UPDATE face_welcome_enrollments
            SET photo_sha256=?, enrolled_at=CURRENT_TIMESTAMP,
                enabled=1, updated_at=CURRENT_TIMESTAMP
            WHERE whatsapp_mobile=? AND consent_status='ACCEPTED'
            """,
            (photo_sha256, whatsapp_mobile),
        )

    def revoke(self, whatsapp_mobile: str) -> None:
        self.database.execute(
            """
            INSERT INTO face_welcome_enrollments (
                whatsapp_mobile, consent_status, enabled, revoked_at, updated_at
            ) VALUES (?, 'REVOKED', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(whatsapp_mobile) DO UPDATE SET
                consent_status='REVOKED',
                enabled=0,
                photo_sha256=NULL,
                biometric_template_ref=NULL,
                revoked_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            """,
            (whatsapp_mobile,),
        )
