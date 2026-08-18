"""Top-level PODX application flow gate.

This service owns routing precedence across onboarding and every vertical runtime.
It intentionally sits above the composed application stack so profile setup and
active human/deal states cannot be stolen by a lower-priority category runtime.
"""
from __future__ import annotations

from app.services.universal_registration_profile_service import UniversalRegistrationProfileService


class EndToEndAppFlowService:
    """Single entry point for profile-first, state-first PODX conversations.

    Priority:
    1. incomplete/on-going Universal Registration/Profile V2
    2. explicit active deal/clarification state
    3. universal/category intelligence handled by the composed inner service
    """

    ONBOARDING_STEPS = {
        "START",
        "WAITING_MOBILE",       # legacy migration only
        "WAITING_NAME",
        "WAITING_LANGUAGE",
        "WAITING_AREA",
        "WAITING_CAPABILITIES", # legacy migration only
    }

    def __init__(self, inner_service, base_conversation=None, response_commands=None) -> None:
        self.inner = inner_service
        self.base_conversation = base_conversation or getattr(inner_service, "base_conversation", None)
        self.response_commands = response_commands or getattr(inner_service, "response_commands", None)
        users = getattr(self.base_conversation, "user_repository", None)
        sessions = getattr(self.base_conversation, "session_registry", None)
        self.registration_v2 = (
            UniversalRegistrationProfileService(users, sessions)
            if users is not None and sessions is not None
            else None
        )

    def process(self, sender_mobile: str, message: str) -> str:
        clean = str(message or "").strip()

        if self._needs_profile_flow(sender_mobile):
            if self.registration_v2 is not None:
                return self.registration_v2.process(sender_mobile=sender_mobile, message=clean)
            if self.base_conversation is not None:
                return self.base_conversation.process(sender_mobile=sender_mobile, message=clean)

        # Absolute state-first gate. Buyer/seller doubt, negotiation, confirm,
        # revision and contact actions execute before ride/product/RFQ/etc.
        if self.response_commands is not None:
            response = self.response_commands.process_text(
                sender_mobile=sender_mobile,
                message=clean,
            )
            if response is not None:
                return response

        return self.inner.process(sender_mobile=sender_mobile, message=clean)

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

        # START for an already registered user is not onboarding: the normal
        # welcome-back path may handle it naturally.
        if step_name == "START":
            return False
        return step_name in self.ONBOARDING_STEPS
