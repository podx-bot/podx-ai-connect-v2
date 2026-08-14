"""Handle universal match responses and Lead Conversion V1.

Lifecycle:
INTERESTED -> seller CONFIRM/DECLINE -> buyer address -> qualified lead ->
optional buyer-requested contact exchange. Button IDs remain internal.
"""

from __future__ import annotations

import re
from typing import Any, Optional


class UniversalResponseCommandService:
    INTEREST_WORDS = {
        "interested", "interest", "yes interested", "i am interested",
        "i'm interested", "వస్తాను", "చేస్తాను", "ఇస్తాను", "కావాలి",
        "సరే చేస్తాను", "నేను వస్తాను", "నేను చేస్తాను", "నేను ఇస్తాను",
        "haan", "ha", "karunga", "aaunga", "de sakta hu", "de sakta hoon",
    }
    CONFIRM_WORDS = {
        "confirm", "yes", "ok", "okay", "continue", "సరే", "ఓకే", "అవును",
        "కొనసాగించండి", "haan", "theek hai",
    }
    DECLINE_WORDS = {
        "decline", "reject", "no", "cancel", "not interested", "వద్దు", "లేదు",
        "క్యాన్సిల్", "ఆసక్తి లేదు", "నో", "nahi", "mat karo",
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

        explicit_not_interest = re.match(r"^(?:not_interested|not interested)\s*#?(\d+)\s*$", text, re.I)
        if explicit_not_interest:
            return "సరే. ఈ matchని skip చేశాను."

        explicit_confirm = re.match(r"^(?:confirm|yes|ok|okay)\s*#?(\d+)\s*$", text, re.I)
        if explicit_confirm:
            return self._seller_decision(sender_mobile, int(explicit_confirm.group(1)), True)

        explicit_decline = re.match(r"^(?:decline|reject|no|cancel)\s*#?(\d+)\s*$", text, re.I)
        if explicit_decline:
            return self._seller_decision(sender_mobile, int(explicit_decline.group(1)), False)

        explicit_contact = re.match(r"^contact\s*#?(\d+)\s*$", text, re.I)
        if explicit_contact:
            return self._contact(sender_mobile, int(explicit_contact.group(1)))

        explicit_done = re.match(r"^done\s*#?(\d+)\s*$", text, re.I)
        if explicit_done:
            return "✅ సరే. Lead details save అయ్యాయి. అవసరం అయితే తర్వాత sellerతో మాట్లాడవచ్చు."

        # After seller confirms, the very next normal buyer message is treated as delivery address.
        waiting_address = self.notification_repository.latest_waiting_address_for_responder(sender_mobile)
        if waiting_address and not self._looks_like_command(text):
            return self._save_address(
                sender_mobile,
                int(waiting_address["request_id"]),
                text,
            )

        pending_target = self.notification_repository.latest_sent_request_for_target(sender_mobile)
        if pending_target and self._is_interest(text):
            return self._interest(sender_mobile, int(pending_target["request_id"]))
        if pending_target and self._is_decline(text):
            return "సరే. ఈ matchని skip చేశాను."

        pending_consent = self.notification_repository.latest_pending_interest_for_requester(sender_mobile)
        if pending_consent:
            request_id = int(pending_consent["request_id"])
            if self._is_confirm(text):
                return self._seller_decision(sender_mobile, request_id, True)
            if self._is_decline(text):
                return self._seller_decision(sender_mobile, request_id, False)

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
            return "✅ మీ interest పంపించాను. Seller confirm చేస్తే PODX వెంటనే next stepకి తీసుకెళ్తుంది."
        return "మీ interest save చేశాను."

    def _seller_decision(self, requester_mobile: str, request_id: int, accepted: bool) -> str:
        pending = self.notification_repository.latest_pending_interest_for_requester(requester_mobile)
        if not pending or int(pending.get("request_id") or 0) != int(request_id):
            return "ఈ requestకి pending confirmation దొరకలేదు."
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        if str(request.get("user_id")) != str(requester_mobile):
            return "ఈ leadని confirm చేసే permission మీకు లేదు."

        result = self.notifications.confirm_lead(
            request=request,
            responder_user_id=str(pending["responder_user_id"]),
            accepted=accepted,
        )
        status = result.get("status")
        if status == "WAITING_BUYER_ADDRESS":
            return "✅ Lead confirm చేశారు. ఇక buyer delivery details PODX collect చేస్తుంది; మీరు wait చేయండి."
        if status == "DECLINED":
            return "సరే. ఈ leadని decline చేశాను."
        if status == "INTEREST_NOT_FOUND":
            return "ఈ buyer interest record దొరకలేదు."
        return "మీ response save చేశాను."

    def _save_address(self, responder_mobile: str, request_id: int, address: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        result = self.notifications.qualify_lead(
            request=request,
            responder_user_id=responder_mobile,
            delivery_address=address,
        )
        status = result.get("status")
        if status == "ADDRESS_TOO_SHORT":
            return "Delivery address ఇంకొంచెం పూర్తి వివరంగా పంపండి — House/Street, Area, Town, Pincode."
        if status == "QUALIFIED_LEAD":
            return "✅ Delivery address save అయింది. Sellerకి qualified lead పంపాను."
        if status == "LEAD_NOT_CONFIRMED":
            return "Seller confirmation ఇంకా complete కాలేదు."
        return "Delivery details save చేశాను."

    def _contact(self, responder_mobile: str, request_id: int) -> str:
        interest = self.notification_repository.latest_qualified_interest_for_responder(responder_mobile)
        if not interest or int(interest.get("request_id") or 0) != int(request_id):
            return "ఈ leadకి contact option ప్రస్తుతం available లేదు."
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        result = self.notifications.share_contacts_after_confirmation(
            request=request,
            responder_user_id=responder_mobile,
        )
        status = result.get("status")
        if status == "CONTACT_SHARED":
            return "✅ Seller contact share చేశాను. Sellerకి కూడా మీ contact పంపాను."
        if status == "ALREADY_SHARED":
            return "ఈ lead contact details ఇప్పటికే share అయ్యాయి."
        if status == "LEAD_NOT_QUALIFIED":
            return "ముందుగా delivery details complete చేయండి."
        if status == "SELLER_NOT_CONFIRMED":
            return "Seller ఇంకా lead confirm చేయలేదు."
        if status == "CONTACT_SHARE_PARTIAL_FAILURE":
            return "Contact shareలో delivery సమస్య వచ్చింది."
        return "Contact request save చేశాను."

    @classmethod
    def _is_interest(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in cls.INTEREST_WORDS or any(
            word in lowered for word in ("interested", "వస్తాను", "చేస్తాను", "ఇస్తాను")
        )

    @classmethod
    def _is_confirm(cls, text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in cls.CONFIRM_WORDS

    @classmethod
    def _is_decline(cls, text: str) -> bool:
        return text.lower().strip() in cls.DECLINE_WORDS

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        lowered = text.lower().strip()
        return any(
            lowered.startswith(prefix)
            for prefix in (
                "interested", "not_interested", "confirm", "decline", "reject",
                "cancel", "contact", "done", "status", "menu", "help", "reset",
            )
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
