"""Handle role-safe Universal Match + Product Conversion V3 responses."""
from __future__ import annotations
import re
from typing import Any, Optional


class UniversalResponseCommandService:
    CONFIRM_WORDS = {"confirm", "yes", "ok", "okay", "సరే", "ఓకే", "అవును", "haan", "theek hai"}
    DECLINE_WORDS = {"decline", "reject", "no", "cancel", "not interested", "వద్దు", "లేదు", "క్యాన్సిల్", "ఆసక్తి లేదు", "నో", "nahi", "mat karo"}

    def __init__(self, demand_repository, notification_service, notification_repository) -> None:
        self.demands = demand_repository
        self.notifications = notification_service
        self.notification_repository = notification_repository

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = self._clean(message)
        if not text:
            return None

        patterns = [
            (r"^BUY_INTERESTED\s+(\d+)\s+(\S+)\s*$", lambda m: self._buyer_interest(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^BUY_NOT_INTERESTED\s+(\d+)\s+(\S+)\s*$", lambda m: "సరే 👍 ఈ sellerని skip చేశాను."),
            (r"^SELLER_CONFIRM\s+(\d+)\s+(\S+)\s*$", lambda m: self._seller_decision(sender_mobile, int(m.group(1)), m.group(2), True)),
            (r"^SELLER_DECLINE\s+(\d+)\s+(\S+)\s*$", lambda m: self._seller_decision(sender_mobile, int(m.group(1)), m.group(2), False)),
            (r"^ORDER_CONTINUE\s+(\d+)\s+(\S+)\s*$", lambda m: self._start_order(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^DIRECT_TALK\s+(\d+)\s+(\S+)\s*$", lambda m: self._direct_talk(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^FINAL_CONFIRM\s+(\d+)\s+(\S+)\s*$", lambda m: self._final_order(sender_mobile, int(m.group(1)), m.group(2), True)),
            (r"^FINAL_CANCEL\s+(\d+)\s+(\S+)\s*$", lambda m: self._final_order(sender_mobile, int(m.group(1)), m.group(2), False)),
            (r"^DONE(?:\s+(\d+))?(?:\s+(\S+))?\s*$", lambda m: "✅ సరే. PODX order details save అయ్యాయి."),
        ]
        for pattern, handler in patterns:
            match = re.match(pattern, text, re.I)
            if match:
                return handler(match)

        waiting = self.notification_repository.latest_waiting_address_for_buyer(sender_mobile)
        if waiting and not self._looks_like_command(text):
            return self._save_address(sender_mobile, int(waiting["request_id"]), str(waiting["responder_user_id"]), text)

        pending = self.notification_repository.latest_pending_interest_for_seller(sender_mobile)
        if pending:
            request_id = int(pending["request_id"])
            buyer = str(pending["requester_user_id"])
            if self._is_confirm(text):
                return self._seller_decision(sender_mobile, request_id, buyer, True)
            if self._is_decline(text):
                return self._seller_decision(sender_mobile, request_id, buyer, False)

        legacy = re.match(r"^(?:INTERESTED|INTEREST)\s*#?(\d+)\s*$", text, re.I)
        if legacy:
            request = self.demands.get(int(legacy.group(1)))
            if request and str(request.get("side") or "").upper() == "OFFER":
                return self._buyer_interest(sender_mobile, int(legacy.group(1)), str(request.get("user_id")))
            return "ఈ పాత match button expire అయింది. కొత్త match notificationలోని button ఉపయోగించండి."
        if re.match(r"^(?:NOT_INTERESTED|NOT INTERESTED)\s*#?(\d+)\s*$", text, re.I):
            return "సరే 👍 ఈ matchని skip చేశాను."
        return None

    def _buyer_interest(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request or str(request.get("status") or "").upper() != "ACTIVE":
            return "ఈ PODX match ఇప్పుడు activeలో లేదు."
        try:
            expected_buyer, expected_seller = self.notifications.resolve_roles(
                request,
                seller if str(request.get("side") or "").upper() == "NEED" else buyer,
            )
        except ValueError:
            return "ఈ match role details సరైనవి కావు."
        if str(expected_buyer) != str(buyer) or str(expected_seller) != str(seller):
            return "ఈ match మీకు సంబంధించినది కాదు."
        result = self.notifications.register_interest(request, buyer, seller)
        if result.get("status") == "WAITING_SELLER_CONFIRM":
            return "✅ మీ ఆసక్తి sellerకి పంపాను. Seller confirm చేసిన వెంటనే next options మీకు వస్తాయి."
        return "✅ మీ ఆసక్తి save చేశాను."

    def _seller_decision(self, seller: str, request_id: int, buyer: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        interest = self.notification_repository.get_interest(request_id, seller)
        if not interest or str(interest.get("requester_user_id")) != str(buyer):
            return "ఈ seller confirmationకి pending buyer interest దొరకలేదు."
        status = self.notifications.confirm_lead(request, buyer, seller, accepted).get("status")
        if status == "READY_FOR_BUYER":
            return "✅ Confirm అయింది. Buyerకి Order Continue / Direct Talk options పంపాను."
        if status == "DECLINED":
            return "సరే. ఈ buyer requestని decline చేశాను."
        return "మీ response save చేశాను."

    def _start_order(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        status = self.notifications.start_order(request, buyer, seller).get("status")
        if status == "WAITING_BUYER_ADDRESS":
            return "📍 Order continue చేస్తున్నాను. మీ delivery address పంపండి."
        if status == "PRICE_REQUIRED":
            return "💰 ఈ productకి seller price ఇంకా confirm కాలేదు. Price తెలియకుండా order continue చేయను; seller price వచ్చిన తర్వాత కొనసాగిద్దాం."
        if status == "SELLER_NOT_CONFIRMED":
            return "Seller confirmation ఇంకా complete కాలేదు."
        return "Order step save చేశాను."

    def _save_address(self, buyer: str, request_id: int, seller: str, address: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        status = self.notifications.qualify_lead(request, buyer, seller, address).get("status")
        if status == "ADDRESS_TOO_SHORT":
            return "Delivery address ఇంకొంచెం పూర్తి వివరంగా పంపండి — House/Street, Area, Town, Pincode."
        if status == "WAITING_FINAL_CONFIRM":
            return "✅ Address save అయింది. Final Order Summary పంపాను — అన్ని వివరాలు చూసి Confirm Order నొక్కండి."
        if status == "LEAD_NOT_CONFIRMED":
            return "Seller confirmation లేదా Order Continue step ఇంకా complete కాలేదు."
        return "Delivery details save చేశాను."

    def _final_order(self, buyer: str, request_id: int, seller: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        status = self.notifications.final_confirm(request, buyer, seller, accepted).get("status")
        if status == "CONVERTED":
            return "✅ Order Confirmed. Sellerకి final confirmed order పంపాను."
        if status == "CANCELLED":
            return "❌ Order cancel చేశాను. Sellerకి confirmed orderగా పంపలేదు."
        if status == "FINAL_CONFIRM_NOT_READY":
            return "Final order confirmation ఇంకా ready కాలేదు. ముందుగా address/order summary complete చేయండి."
        return "Final order response save చేశాను."

    def _direct_talk(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        status = self.notifications.share_contacts_after_confirmation(request, buyer, seller).get("status")
        return {
            "CONTACT_SHARED": "✅ Seller contact మీకు పంపాను. Sellerకి కూడా మీ contact పంపాను.",
            "ALREADY_SHARED": "ఈ match contact details ఇప్పటికే share అయ్యాయి.",
            "SELLER_NOT_CONFIRMED": "Seller ఇంకా confirm చేయలేదు.",
            "CONTACT_SHARE_PARTIAL_FAILURE": "Contact shareలో delivery సమస్య వచ్చింది.",
        }.get(status, "Direct Talk request save చేశాను.")

    @classmethod
    def _is_confirm(cls, text: str) -> bool:
        return text.lower().strip() in cls.CONFIRM_WORDS

    @classmethod
    def _is_decline(cls, text: str) -> bool:
        return text.lower().strip() in cls.DECLINE_WORDS

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        return any(
            text.lower().strip().startswith(prefix)
            for prefix in (
                "buy_interested", "buy_not_interested", "seller_confirm", "seller_decline",
                "order_continue", "direct_talk", "final_confirm", "final_cancel", "interested",
                "not_interested", "confirm", "decline", "reject", "cancel", "contact", "done",
                "status", "menu", "help", "reset",
            )
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
