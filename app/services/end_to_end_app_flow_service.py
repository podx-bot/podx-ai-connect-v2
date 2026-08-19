"""Top-level PODX application flow gate.

This service owns routing precedence across onboarding and every vertical runtime.
It intentionally sits above the composed application stack so profile setup and
active human/deal states cannot be stolen by a lower-priority category runtime.
"""
from __future__ import annotations

from app.repositories.face_welcome_repository import FaceWelcomeRepository
from app.services.face_welcome_enrollment_service import FaceWelcomeEnrollmentService
from app.services.universal_registration_profile_service import UniversalRegistrationProfileService


class EndToEndAppFlowService:
    """Single entry point for profile-first, state-first PODX conversations."""

    ONBOARDING_STEPS = {
        "START",
        "WAITING_MOBILE",
        "WAITING_NAME",
        "WAITING_LANGUAGE",
        "WAITING_AREA",
        "WAITING_CAPABILITIES",
    }

    def __init__(self, inner_service, base_conversation=None, response_commands=None) -> None:
        self.inner = inner_service
        self.base_conversation = base_conversation or getattr(inner_service, "base_conversation", None)
        self.response_commands = response_commands or getattr(inner_service, "response_commands", None)
        users = getattr(self.base_conversation, "user_repository", None)
        sessions = getattr(self.base_conversation, "session_registry", None)
        self.sessions = sessions
        self.registration_v2 = (
            UniversalRegistrationProfileService(users, sessions)
            if users is not None and sessions is not None
            else None
        )
        database = getattr(users, "database", None)
        self.face_welcome = None
        if database is not None:
            try:
                self.face_welcome = FaceWelcomeEnrollmentService(FaceWelcomeRepository(database))
            except Exception:
                self.face_welcome = None

    def process(self, sender_mobile: str, message: str) -> str:
        clean = str(message or "").strip()

        if self._needs_profile_flow(sender_mobile):
            if self.registration_v2 is not None:
                return self.registration_v2.process(sender_mobile=sender_mobile, message=clean)
            if self.base_conversation is not None:
                return self.base_conversation.process(sender_mobile=sender_mobile, message=clean)

        face_handoff = self._process_face_welcome_handoff(sender_mobile, clean)
        if face_handoff is not None:
            return face_handoff

        if self.response_commands is not None:
            response = self.response_commands.process_text(
                sender_mobile=sender_mobile,
                message=clean,
            )
            if response is not None:
                return response

        return self.inner.process(sender_mobile=sender_mobile, message=clean)

    def _process_face_welcome_handoff(self, sender_mobile: str, message: str) -> str | None:
        if self.sessions is None or self.face_welcome is None:
            return None
        try:
            session = self.sessions.get(sender_mobile)
            data = getattr(session, "data", None)
            if not isinstance(data, dict) or not data.get("face_welcome_handoff_pending"):
                return None

            normalized = " ".join(str(message or "").strip().lower().split())
            yes_words = {"yes", "ok", "అవును", "సరే", "हाँ", "हां"}
            no_words = {"no", "వద్దు", "ఇప్పుడు వద్దు", "not now", "skip", "अभी नहीं", "नहीं"}

            if normalized in yes_words:
                reply = self.face_welcome.process_text(sender_mobile, normalized)
                data["face_welcome_handoff_pending"] = False
                data["face_welcome_photo_pending"] = True
                self._save_session(sender_mobile)
                return reply or self.face_welcome.photo_prompt()

            if normalized in no_words:
                reply = self.face_welcome.process_text(sender_mobile, "వద్దు")
                data["face_welcome_handoff_pending"] = False
                data["face_welcome_photo_pending"] = False
                self._save_session(sender_mobile)
                return (reply or "సరే. Face Welcome skip చేశాను.") + "\n\nఇప్పుడు మీకు ఏం కావాలో మీ మాటల్లో చెప్పండి — voiceగా లేదా textగా."

            return "Face Welcome optional. దయచేసి ‘అవును’ లేదా ‘ఇప్పుడు వద్దు’ అని చెప్పండి."
        except Exception:
            return None

    def _save_session(self, sender_mobile: str) -> None:
        save = getattr(self.sessions, "save", None)
        if callable(save):
            save(sender_mobile)

    def _needs_profile_flow(self, sender_mobile: str) -> bool:
        base = self.base_conversation
        users = getattr(base, "user_repository", None)
        sessions = getattr(base, "session_registry", None)
        if users is None:
            return False

        user = users.find_by_whatsapp_mobile(sender_mobile)
        if not user or int(user.get("registration_complete") or 0) != 1:
            return True

        if sessions is None:
            return False
        try:
            step = sessions.get(sender_mobile).step
            step_name = str(getattr(step, "name", step))
        except Exception:
            return False

        if step_name == "START":
            return False
        return step_name in self.ONBOARDING_STEPS
