"""Handle role-safe Universal Match + Lead Conversion V1 responses.

Canonical lifecycle:
Buyer Interested -> Seller Confirm/Decline -> Buyer Order Continue/Direct Talk ->
Buyer Address -> Seller Qualified Lead. Button ids carry internal request/seller
or request/buyer ids so technical ids never need to be typed by customers.
"""

from __future__ import annotations

import re
from typing import Any, Optional


class UniversalResponseCommandService:
    INTEREST_WORDS = {
        "interested", "interest", "yes interested", "i am interested", "i'm interested",
        "ఆసక్తి ఉంది", "కావాలి", "నాకు కావాలి", "haan", "ha",
    }
    CONFIRM_WORDS = {
        "confirm", "yes", "ok", "okay", "సరే", "ఓకే", "అవును", "haan", "theek hai",
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

        # New interactive buttons: internal ids carry the role counterparty.
        match = re.match(r"^BUY_INTERESTED\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return self._buyer_interest(sender_mobile, int(match.group(1)), match.group(2))

        match = re.match(r"^BUY_NOT_INTERESTED\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return "సరే 👍 ఈ sellerని skip చేశాను."

        match = re.match(r"^SELLER_CONFIRM\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return self._seller_decision(sender_mobile, int(match.group(1)), match.group(2), True)

        match = re.match(r"^SELLER_DECLINE\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return self._seller_decision(sender_mobile, int(match.group(1)), match.group(2), False)

        match = re.match(r"^ORDER_CONTINUE\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return self._start_order(sender_mobile, int(match.group(1)), match.group(2))

        match = re.match(r"^DIRECT_TALK\s+(\d+)\s+(\S+)\s*$", text, re.I)
        if match:
            return self._direct_talk(sender_mobile, int(match.group(1)), match.group(2))

        match = re.match(r"^DONE(?:\s+(\d+))?(?:\s+(\S+))?\s*$", text, re.I)
        if match:
            return "✅ సరే. PODX order details save అయ్యాయి."

        # Buyer address capture only after Buyer explicitly selected Order Continue.
        waiting_address = self.notification_repository.latest_waiting_address_for_buyer(sender_mobile)
        if waiting_address and not self._looks_like_command(text):
            return self._save_address(
                buyer_mobile=sender_mobile,
                request_id=int(waiting_address["request_id"]),
                seller_mobile=str(waiting_address["responder_user_id"]),
                address=text,
            )

        # Natural-language seller fallback after a pending buyer selection.
        pending_seller = self.notification_repository.latest_pending_interest_for_seller(sender_mobile)
        if pending_seller:
            request_id = int(pending_seller["request_id"])
            buyer_mobile = str(pending_seller["requester_user_id"])
            if self._is_confirm(text):
                return self._seller_decision(sender_mobile, request_id, buyer_mobile, True)
            if self._is_decline(text):
                return self._seller_decision(sender_mobile, request_id, buyer_mobile, False)

        # Legacy compatibility for OFFER-origin notifications where seller is the request owner.
        legacy_interest = re.match(r"^(?:INTERESTED|INTEREST)\s*#?(\d+)\s*$", text, re.I)
        if legacy_interest:
            request_id = int(legacy_interest.group(1))
            request = self.demands.get(request_id)
            if request and str(request.get("side") or "").upper() == "OFFER":
                return self._buyer_interest(sender_mobile, request_id, str(request.get("user_id")))
            return "ఈ పాత match button expire అయింది. కొత్త match notificationలోని button ఉపయోగించండి."

        legacy_no = re.match(r"^(?:NOT_INTERESTED|NOT INTERESTED)\s*#?(\d+)\s*$", text, re.I)
        if legacy_no:
            return "సరే 👍 ఈ matchని skip చేశాను."

        return None

    def _buyer_interest(self, buyer_mobile: str, request_id: int, seller_mobile: str) -> str:
        request = self.demands.get(request_id)
        if not request or str(request.get("status") or "").upper() != "ACTIVE":
            return "ఈ PODX match ఇప్పుడు activeలో లేదు."
        try:
            expected_buyer, expected_seller = self.notifications.resolve_roles(request, seller_mobile if str(request.get("side") or "").upper() == "NEED" else buyer_mobile)
        except ValueError:
            return "ఈ match role details సరైనవి కావు."
        if str(expected_buyer) != str(buyer_mobile) or str(expected_seller) != str(seller_mobile):
            return "ఈ match మీకు సంబంధించినది కాదు."

        result = self.notifications.register_interest(request, buyer_mobile, seller_mobile)
        if result.get("status") == "WAITING_SELLER_CONFIRM":
            return "✅ మీ ఆసక్తి sellerకి పంపాను. Seller confirm చేసిన వెంటనే next options మీకు వస్తాయి."
        if result.get("status") == "ROLE_MISMATCH":
            return "ఈ match role verification fail అయింది."
        return "✅ మీ ఆసక్తి save చేశాను."

    def _seller_decision(self, seller_mobile: str, request_id: int, buyer_mobile: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        interest = self.notification_repository.get_interest(request_id, seller_mobile)
        if not interest or str(interest.get("requester_user_id")) != str(buyer_mobile):
            return "ఈ seller confirmationకి pending buyer interest దొరకలేదు."

        result = self.notifications.confirm_lead(
            request=request,
            buyer_user_id=buyer_mobile,
            seller_user_id=seller_mobile,
            accepted=accepted,
        )
        status = result.get("status")
        if status == "READY_FOR_BUYER":
            return "✅ Confirm అయింది. Buyerకి Order Continue / Direct Talk options పంపాను."
        if status == "DECLINED":
            return "సరే. ఈ buyer requestని decline చేశాను."
        if status == "INTEREST_NOT_FOUND":
            return "ఈ buyer interest record దొరకలేదు."
        return "మీ response save చేశాను."

    def _start_order(self, buyer_mobile: str, request_id: int, seller_mobile: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        result = self.notifications.start_order(request, buyer_mobile, seller_mobile)
        if result.get("status") == "WAITING_BUYER_ADDRESS":
            return "📍 Order continue చేస్తున్నాను. మీ delivery address పంపండి."
        if result.get("status") == "SELLER_NOT_CONFIRMED":
            return "Seller confirmation ఇంకా complete కాలేదు."
        return "Order step save చేశాను."

    def _save_address(self, buyer_mobile: str, request_id: int, seller_mobile: str, address: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        result = self.notifications.qualify_lead(
            request=request,
            buyer_user_id=buyer_mobile,
            seller_user_id=seller_mobile,
            delivery_address=address,
        )
        status = result.get("status")
        if status == "ADDRESS_TOO_SHORT":
            return "Delivery address ఇంకొంచెం పూర్తి వివరంగా పంపండి — House/Street, Area, Town, Pincode."
        if status == "QUALIFIED_LEAD":
            return "✅ Delivery address save అయింది. Sellerకి పూర్తి Qualified Order Lead పంపాను."
        if status == "LEAD_NOT_CONFIRMED":
            return "Seller confirmation లేదా Order Continue step ఇంకా complete కాలేదు."
        return "Delivery details save చేశాను."

    def _direct_talk(self, buyer_mobile: str, request_id: int, seller_mobile: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        result = self.notifications.share_contacts_after_confirmation(
            request=request,
            buyer_user_id=buyer_mobile,
            seller_user_id=seller_mobile,
        )
        status = result.get("status")
        if status == "CONTACT_SHARED":
            return "✅ Seller contact మీకు పంపాను. Sellerకి కూడా మీ contact పంపాను."
        if status == "ALREADY_SHARED":
            return "ఈ match contact details ఇప్పటికే share అయ్యాయి."
        if status == "SELLER_NOT_CONFIRMED":
            return "Seller ఇంకా confirm చేయలేదు."
        if status == "CONTACT_SHARE_PARTIAL_FAILURE":
            return "Contact shareలో delivery సమస్య వచ్చింది."
        return "Direct Talk request save చేశాను."

    @classmethod
    def _is_confirm(cls, text: str) -> bool:
        return text.lower().strip() in cls.CONFIRM_WORDS

    @classmethod
    def _is_decline(cls, text: str) -> bool:
        return text.lower().strip() in cls.DECLINE_WORDS

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        lowered = text.lower().strip()
        return any(
            lowered.startswith(prefix)
            for prefix in (
                "buy_interested", "buy_not_interested", "seller_confirm", "seller_decline",
                "order_continue", "direct_talk", "interested", "not_interested", "confirm",
                "decline", "reject", "cancel", "contact", "done", "status", "menu", "help", "reset",
            )
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
