from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FaceWelcomeStatus(str, Enum):
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED = "ENROLLED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class FaceWelcomeProfile:
    user_id: str
    status: FaceWelcomeStatus = FaceWelcomeStatus.NOT_ENROLLED
    consent_active: bool = False
    face_template_id: Optional[str] = None
    display_name: Optional[str] = None


@dataclass(frozen=True)
class FaceWelcomeDecision:
    allow_match: bool
    greeting: Optional[str]
    reason: str


class FaceWelcomePolicyService:
    """Consent-first policy layer for in-store Face Welcome.

    This service intentionally stores only references to biometric templates.
    Raw photos are not part of this profile contract and should not be exposed
    to business users as a browsable customer-photo database.
    """

    def enroll(
        self,
        *,
        user_id: str,
        explicit_consent: bool,
        face_template_id: Optional[str],
        display_name: Optional[str] = None,
    ) -> FaceWelcomeProfile:
        if not explicit_consent:
            return FaceWelcomeProfile(
                user_id=user_id,
                status=FaceWelcomeStatus.NOT_ENROLLED,
                consent_active=False,
                face_template_id=None,
                display_name=display_name,
            )
        if not face_template_id:
            raise ValueError("face_template_id is required after explicit consent")
        return FaceWelcomeProfile(
            user_id=user_id,
            status=FaceWelcomeStatus.ENROLLED,
            consent_active=True,
            face_template_id=face_template_id,
            display_name=display_name,
        )

    def disable(self, profile: FaceWelcomeProfile) -> FaceWelcomeProfile:
        return FaceWelcomeProfile(
            user_id=profile.user_id,
            status=FaceWelcomeStatus.DISABLED,
            consent_active=False,
            face_template_id=None,
            display_name=profile.display_name,
        )

    def evaluate_match(
        self,
        *,
        profile: FaceWelcomeProfile,
        biometric_match: bool,
    ) -> FaceWelcomeDecision:
        if profile.status is not FaceWelcomeStatus.ENROLLED:
            return FaceWelcomeDecision(False, None, "face_welcome_not_enrolled")
        if not profile.consent_active:
            return FaceWelcomeDecision(False, None, "face_welcome_consent_inactive")
        if not profile.face_template_id:
            return FaceWelcomeDecision(False, None, "face_template_missing")
        if not biometric_match:
            return FaceWelcomeDecision(False, None, "face_not_matched")

        name = (profile.display_name or "").strip()
        greeting = f"Welcome {name}!" if name else "Welcome!"
        return FaceWelcomeDecision(True, greeting, "face_match_confirmed")
