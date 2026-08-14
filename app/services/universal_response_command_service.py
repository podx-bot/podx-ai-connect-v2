"""Parse live WhatsApp responses for Universal Flow V1.

This service intentionally handles only the small response lifecycle after a
universal request has already been created/notified: INTERESTED -> requester
consent -> contact exchange. It returns None for unrelated text so the normal
conversation router can continue.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


class UniversalResponseCommandService:
    INTEREST_WORDS = {
        "interested", "interest", "yes interested", "i am interested",
        "i'm interested", "వస్తాను", "చేస్తాను", "ఇస్తాను", "కావాలి",
        "సరే చేస్తాను", "నేను వస్తాను", "నేను చేస్తాను", "నేను ఇస్తాను",
        "haan", "ha", "karunga", "aaunga", "de sakta hu", "de sakta hoon",
    }
    CONFIRM_WORDS = {
        "confirm", "yes", "ok", "okay", "share", "share contact",
        "contact share", "సరే", "ఓకే", "అవును", "షేర్ చేయండి",
        "కాంటాక్ట్ షేర్ చేయండి", "haan", "theek hai",
    }
    DECLINE_WORDS = {
        "decline", "reject", "no", "cancel", "వద్దు", "లేదు", "క్యాన్సిల్",
        "నో", "nahi", "mat karo",
    }

    def __init__(self, demand_repository, notification_service, notification_repository) -> None:
        self.demands = demand_repository
        self.notifications = notification_service
        self.notification_repository = notification_repository

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = self._clean(message)
        if not text:
            return None

        explicit_interest = re.match(r"^(?:interested|interest)\s*#?(\d+)\s*$", text, re.I)
        if explicit_interest:
            return self._interest(sender_mobile, int(explicit_interest.group(1)))

        explicit_confirm = re.match(
            r"^(?:confirm|share|yes|ok|okay)\s*#?(\d+)\s+([^\s]+)\s*$",
            text,
            re.I,
        )
        if explicit_confirm:
            return self._consent(
                sender_mobile,
                int(explicit_confirm.group(1)),
                explicit_confirm.group(2),
                accepted=True,
            )

        explicit_decline = re.match(
            r"^(?:decline|reject|no|cancel)\s*#?(\d+)\s+([^\s]+)\s*$",
            text,
            re.I,
        )
        if explicit_decline:
            return self._consent(
                sender_mobile,
                int(explicit_decline.group(1)),
                explicit_decline.group(2),
                accepted=False,
            )

        pending_target = self.notification_repository.latest_sent_request_for_target(sender_mobile)
        if pending_target and self._is_interest(text):
            return self._interest(sender_mobile, int(pending_target["request_id"]))

        pending_consent = self.notification_repository.latest_pending_interest_for_requester(sender_mobile)
        if pending_consent:
            request_id = int(pending_consent["request_id"])
            responder = str(pending_consent["responder_user_id"])
            if self._is_confirm(text):
                return self._consent(sender_mobile, request_id, responder, accepted=True)
            if self._is_decline(text):
                return self._consent(sender_mobile, request_id, responder, accepted=False)

        return None

    def _interest(self, responder_mobile: str, request_id: int) -> str:
        request = self.demands.get(request_id)
        if not request or str(request.get("status") or "").upper() != "ACTIVE":
            return "ఈ PODX request ఇప్పుడు activeలో లేదు."
        if str(request.get("user_id")) == str(responder_mobile):
            return "ఇది మీ స్వంత request."
        if not self.notification_repository.was_targeted(request_id, responder_mobile):
            return "ఈ request మీకు పంపబడిన notificationగా కనిపించడం లేదు."

        result = self.notifications.register_interest(request, responder_mobile)
        if result.get("status") == "WAITING_REQUESTER_CONSENT":
            return "✅ మీ interest పంపించాను. అవతలి వ్యక్తి contact shareకి confirm చేస్తే వెంటనే మీకు చెప్తాను."
        return "మీ interest save చేశాను."

    def _consent(self, requester_mobile: str, request_id: int, responder_mobile: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        if str(request.get("user_id")) != str(requester_mobile):
            return "ఈ requestకి contact share confirm చేసే permission మీకు లేదు."

        result = self.notifications.confirm_and_share_contacts(
            request=request,
            responder_user_id=responder_mobile,
            accepted=accepted,
        )
        status = result.get("status")
        if status == "CONTACT_SHARED":
            return "✅ ఇద్దరికీ contact details share చేశాను. మీరు directగా మాట్లాడుకోవచ్చు."
        if status == "DECLINED":
            return "సరే. ఈ వ్యక్తితో contact share చేయలేదు."
        if status == "ALREADY_SHARED":
            return "ఈ match contact details ఇప్పటికే share అయ్యాయి."
        if status == "INTEREST_NOT_FOUND":
            return "ఈ వ్యక్తి interest record దొరకలేదు."
        if status == "CONTACT_SHARE_PARTIAL_FAILURE":
            return "Contact shareలో ఒక delivery సమస్య వచ్చింది. మళ్లీ ప్రయత్నిస్తాను."
        return "మీ response save చేశాను."

    @classmethod
    def _is_interest(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in cls.INTEREST_WORDS or any(word in lowered for word in ("interested", "వస్తాను", "చేస్తాను", "ఇస్తాను"))

    @classmethod
    def _is_confirm(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in cls.CONFIRM_WORDS or "share చేయ" in lowered or "షేర్ చేయ" in lowered

    @classmethod
    def _is_decline(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in cls.DECLINE_WORDS

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
