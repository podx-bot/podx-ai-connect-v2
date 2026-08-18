"""Handle role-safe Universal Match + Product Conversion responses."""
from __future__ import annotations

import re
from typing import Any, Optional

from app.services.universal_context_router import UniversalContextRouter


class UniversalResponseCommandService:
    INTEREST_WORDS = {
        "interested", "interest", "yes interested", "i am interested", "i'm interested",
        "వస్తాను", "చేస్తాను", "ఇస్తాను", "కావాలి", "సరే చేస్తాను",
        "నేను వస్తాను", "నేను చేస్తాను", "నేను ఇస్తాను",
        "haan", "ha", "karunga", "aaunga", "de sakta hu", "de sakta hoon",
    }
    CONFIRM_WORDS = {
        "confirm", "yes", "ok", "okay", "share", "share contact", "contact share",
        "సరే", "ఓకే", "అవును", "షేర్ చేయండి", "కాంటాక్ట్ షేర్ చేయండి",
        "haan", "theek hai",
    }
    DECLINE_WORDS = {
        "decline", "reject", "no", "cancel", "not interested", "వద్దు", "లేదు",
        "క్యాన్సిల్", "ఆసక్తి లేదు", "నో", "nahi", "mat karo",
    }

    def __init__(
        self,
        demand_repository,
        notification_service,
        notification_repository,
        context_router=None,
    ) -> None:
        self.demands = demand_repository
        self.notifications = notification_service
        self.notification_repository = notification_repository
        self.deals = self._build_deal_service()
        self.context_router = context_router or UniversalContextRouter()

    def _build_deal_service(self):
        try:
            from app.repositories.deal_discussion_repository import DealDiscussionRepository
            from app.services.deal_discussion_service import DealDiscussionService
            db_path = str(getattr(self.notification_repository, "db_path", "podx.db") or "podx.db")
            return DealDiscussionService(
                DealDiscussionRepository(db_path),
                self.notifications.whatsapp,
                self.notifications.contact_resolver,
            )
        except Exception:
            return None

    def _same_deal_context(self, request: dict, text: str) -> bool:
        try:
            return bool(self.context_router.should_consume_as_deal_followup(request, text))
        except Exception:
            return True

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = self._clean(message)
        if not text:
            return None

        patterns = [
            (r"^BUY_INTERESTED\s+(\d+)\s+(\S+)\s*$", lambda m: self._buyer_interest(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^BUY_NOT_INTERESTED\s+(\d+)\s+(\S+)\s*$", lambda m: "సరే 👍 ఈ sellerని skip చేశాను."),
            (r"^SELLER_CONFIRM\s+(\d+)\s+(\S+)\s*$", lambda m: self._seller_decision(sender_mobile, int(m.group(1)), m.group(2), True)),
            (r"^SELLER_DECLINE\s+(\d+)\s+(\S+)\s*$", lambda m: self._seller_decision(sender_mobile, int(m.group(1)), m.group(2), False)),
            (r"^DEAL_CONFIRM\s+(\d+)\s+(\S+)\s*$", lambda m: self._deal_confirm(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^DEAL_CHANGE\s+(\d+)\s+(\S+)\s*$", lambda m: self._deal_change(sender_mobile, int(m.group(1)), m.group(2))),
            (r"^DEAL_QUESTION\s+(\d+)\s+(\S+)\s*$", lambda m: self._deal_question(sender_mobile, int(m.group(1)), m.group(2))),
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

        legacy_interest = re.match(r"^(?:INTERESTED|INTEREST)\s*#?(\d+)\s*$", text, re.I)
        if legacy_interest:
            return self._legacy_interest(sender_mobile, int(legacy_interest.group(1)))

        explicit_confirm = re.match(r"^(?:CONFIRM|SHARE|YES|OK|OKAY)\s*#?(\d+)\s*$", text, re.I)
        if explicit_confirm:
            return self._legacy_consent_for_request(sender_mobile, int(explicit_confirm.group(1)), True)

        explicit_decline = re.match(r"^(?:DECLINE|REJECT|NO|CANCEL)\s*#?(\d+)\s*$", text, re.I)
        if explicit_decline:
            return self._legacy_consent_for_request(sender_mobile, int(explicit_decline.group(1)), False)

        if self.deals is not None and not self._looks_like_command(text):
            buyer_change = self.deals.pending_for_buyer_change(sender_mobile)
            if buyer_change:
                request = self.demands.get(int(buyer_change["request_id"]))
                if request and self._same_deal_context(request, text):
                    reply = self.deals.consume_buyer_change(
                        request,
                        sender_mobile,
                        str(buyer_change["seller_user_id"]),
                        text,
                    )
                    if reply is not None:
                        return reply

            seller_deal = self.deals.pending_for_seller(sender_mobile)
            if seller_deal:
                request = self.demands.get(int(seller_deal["request_id"]))
                if request and self._same_deal_context(request, text):
                    reply = self.deals.consume_seller_text(
                        request,
                        str(seller_deal["buyer_user_id"]),
                        sender_mobile,
                        text,
                    )
                    if reply is not None:
                        return reply

            buyer_summary = self.deals.pending_for_buyer_summary(sender_mobile)
            if buyer_summary and self._looks_like_deal_change(text):
                request = self.demands.get(int(buyer_summary["request_id"]))
                if request and self._same_deal_context(request, text):
                    self.deals.ask_for_change(request, sender_mobile, str(buyer_summary["seller_user_id"]))
                    return self.deals.consume_buyer_change(
                        request,
                        sender_mobile,
                        str(buyer_summary["seller_user_id"]),
                        text,
                    )

        waiting = self.notification_repository.latest_waiting_address_for_buyer(sender_mobile)
        if waiting and not self._looks_like_command(text):
            return self._save_address(
                sender_mobile,
                int(waiting["request_id"]),
                str(waiting["responder_user_id"]),
                text,
            )

        pending = self.notification_repository.latest_pending_interest_for_seller(sender_mobile)
        if pending:
            request_id = int(pending["request_id"])
            buyer = str(pending["requester_user_id"])
            if self._is_confirm(text):
                return self._seller_decision(sender_mobile, request_id, buyer, True)
            if self._is_decline(text):
                return self._seller_decision(sender_mobile, request_id, buyer, False)

        targeted = self.notification_repository.latest_sent_request_for_target(sender_mobile)
        if targeted and self._is_interest(text):
            return self._legacy_interest(sender_mobile, int(targeted["request_id"]))

        pending_consent = self.notification_repository.latest_pending_interest_for_requester(sender_mobile)
        if pending_consent:
            request_id = int(pending_consent["request_id"])
            responder = str(pending_consent["responder_user_id"])
            if self._is_confirm(text):
                return self._legacy_consent(sender_mobile, request_id, responder, True)
            if self._is_decline(text):
                return self._legacy_consent(sender_mobile, request_id, responder, False)

        if re.match(r"^(?:NOT_INTERESTED|NOT INTERESTED)\s*#?(\d+)\s*$", text, re.I):
            return "సరే 👍 ఈ matchని skip చేశాను."
        return None

    def _legacy_interest(self, responder: str, request_id: int) -> str:
        request = self.demands.get(request_id)
        if not request or str(request.get("status") or "").upper() != "ACTIVE":
            return "ఈ PODX request ఇప్పుడు activeలో లేదు."
        if str(request.get("user_id")) == str(responder):
            return "ఇది మీ స్వంత request."
        if not self.notification_repository.was_targeted(request_id, responder):
            return "ఈ request మీకు పంపబడిన notificationగా కనిపించడం లేదు."
        result = self.notifications.register_interest(request, responder)
        if result.get("status") == "WAITING_REQUESTER_CONSENT":
            return "✅ మీ interest పంపించాను. అవతలి వ్యక్తి contact shareకి confirm చేస్తే వెంటనే మీకు చెప్తాను."
        return "మీ interest save చేశాను."

    def _legacy_consent_for_request(self, requester: str, request_id: int, accepted: bool) -> str:
        pending = self.notification_repository.latest_pending_interest_for_requester(requester)
        if not pending or int(pending.get("request_id") or 0) != int(request_id):
            return "ఈ requestకి pending contact confirmation దొరకలేదు."
        return self._legacy_consent(requester, request_id, str(pending["responder_user_id"]), accepted)

    def _legacy_consent(self, requester: str, request_id: int, responder: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        if str(request.get("user_id")) != str(requester):
            return "ఈ requestకి contact share confirm చేసే permission మీకు లేదు."
        result = self.notifications.confirm_and_share_contacts(request, responder, accepted)
        status = result.get("status")
        return {
            "CONTACT_SHARED": "✅ ఇద్దరికీ contact details share చేశాను. మీరు directగా మాట్లాడుకోవచ్చు.",
            "DECLINED": "సరే. ఈ వ్యక్తితో contact share చేయలేదు.",
            "ALREADY_SHARED": "ఈ match contact details ఇప్పటికే share అయ్యాయి.",
            "INTEREST_NOT_FOUND": "ఈ వ్యక్తి interest record దొరకలేదు.",
            "CONTACT_SHARE_PARTIAL_FAILURE": "Contact shareలో ఒక delivery సమస్య వచ్చింది. మళ్లీ ప్రయత్నిస్తాను.",
        }.get(status, "మీ response save చేశాను.")

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
        if not accepted:
            status = self.notifications.confirm_lead(request, buyer, seller, False).get("status")
            if status == "DECLINED":
                return "సరే. ఈ buyer requestని decline చేశాను."
            return "మీ response save చేశాను."
        if self.deals is None:
            return "Deal discussion service ప్రస్తుతం readyగా లేదు. దయచేసి కొద్దిసేపటి తర్వాత retry చేయండి."
        self.notification_repository.set_seller_decision(request_id, seller, True)
        status = self.deals.start(request, buyer, seller).get("status")
        if status == "WAITING_SELLER_DETAILS":
            return "✅ Confirm అయింది. Order/Direct Talkకి ముందు rate, quality, quantity, delivery వంటి missing deal details PODX అడుగుతోంది."
        return "Seller confirmation save చేశాను."

    def _deal_confirm(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request or self.deals is None:
            return "ఈ deal details దొరకలేదు."
        result = self.deals.confirm(request, buyer, seller)
        if result.get("status") == "DEAL_CONFIRMED":
            return "✅ Deal confirm అయింది. Order Continue / Direct Talkకి వెళ్లవచ్చు; కొనడానికి ముందు doubt ఉంటే Sellerని అడగండి option కూడా ఉపయోగించవచ్చు."
        if result.get("status") == "DEAL_NOT_READY":
            return "Deal summary ఇంకా complete కాలేదు. Seller details/clarification పూర్తయ్యాక confirm చేయండి."
        return "ఈ deal మీకు సంబంధించినది కాదు."

    def _deal_change(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request or self.deals is None:
            return "ఈ deal details దొరకలేదు."
        return self.deals.ask_for_change(request, buyer, seller)

    def _deal_question(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request or self.deals is None:
            return "ఈ deal details దొరకలేదు."
        deal = self.deals.repository.get(request_id, seller)
        if not deal or str(deal.get("buyer_user_id")) != str(buyer):
            return "ఈ deal మీకు సంబంధించినది కాదు."
        status = str(deal.get("status") or "")
        if status == "WAITING_BUYER_CHANGE":
            return "💬 మీ doubt మీ మాటల్లో text/voiceలో పంపండి. PODX sellerకి మాత్రమే relay చేస్తుంది."
        if status not in {"CONFIRMED", "WAITING_BUYER_CONFIRM"}:
            return "ఈ deal ఇప్పుడు seller doubt verificationకి readyగా లేదు."
        self.deals.repository.mark_waiting_buyer_change(request_id, seller)
        return (
            "💬 కొనడానికి ముందు ఇంకేమైనా తెలుసుకోవాలా? మీ doubt మీ మాటల్లో text/voiceలో పంపండి. "
            "PODX sellerకి relevant question మాత్రమే relay చేసి answer తెస్తుంది. Contact details privateగానే ఉంటాయి."
        )

    def _request_with_confirmed_deal(self, request: dict, seller: str) -> dict:
        enriched = dict(request)
        if self.deals is None:
            return enriched
        try:
            deal = self.deals.repository.get(int(request["id"]), str(seller))
        except Exception:
            return enriched
        if not deal or deal.get("status") != "CONFIRMED":
            return enriched
        details = dict(deal.get("details") or {})
        rate = details.get("rate")
        if rate is not None:
            enriched["deal_rate"] = rate
            enriched["deal_rate_unit"] = details.get("rate_unit") or details.get("unit") or request.get("unit")
            if str(enriched.get("side") or "").upper() == "OFFER" and enriched.get("price") is None:
                enriched["price"] = rate
        for key in ("quality", "availability", "fulfilment"):
            if details.get(key) not in (None, ""):
                enriched[f"deal_{key}"] = details[key]
        if enriched.get("quantity") is None and details.get("quantity") is not None:
            enriched["quantity"] = details.get("quantity")
            enriched["unit"] = details.get("unit") or enriched.get("unit")
        return enriched

    def _start_order(self, buyer: str, request_id: int, seller: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        if self.deals is not None and not self.deals.is_confirmed(request_id, seller):
            return "🤝 ముందుగా rate/quality/quantity deal discussion complete చేసి Deal OK confirm చేయాలి. అప్పటి వరకు order continue కాదు."
        request = self._request_with_confirmed_deal(request, seller)
        status = self.notifications.start_order(request, buyer, seller).get("status")
        if status == "WAITING_BUYER_ADDRESS":
            return "📍 Order continue చేస్తున్నాను. మీ delivery address పంపండి."
        if status == "PRICE_REQUIRED":
            return "💰 ఈ productకి seller price ఇంకా confirm కాలేదు. Price తెలియకుండా order continue చేయను; seller price వచ్చిన తర్వాత కొనసాగిద్దాం."
        if status == "SELLER_NOT_CONFIRMED":
            return "Seller confirmation ఇంకా complete కాలేదు."
        return "Order step save చేశాను."

    def _send_preorder_options(self, buyer: str, request_id: int, seller: str) -> None:
        sender = getattr(self.notifications, "_send_buttons_or_text", None)
        if not callable(sender):
            return
        try:
            sender(
                buyer,
                "🤔 కొనడానికి ముందు ఇంకేమైనా తెలుసుకోవాలా? Sellerని PODX ద్వారా అడగండి, లేదా Direct Talk ఎంచుకోండి. అన్నీ సరే అయితే Confirm Order చేయండి.",
                [
                    {"id": f"FINAL_CONFIRM {request_id} {seller}", "title": "✅ Confirm Order"},
                    {"id": f"DEAL_QUESTION {request_id} {seller}", "title": "💬 Sellerని అడగండి"},
                    {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"},
                ],
            )
        except Exception:
            return

    def _save_address(self, buyer: str, request_id: int, seller: str, address: str) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        request = self._request_with_confirmed_deal(request, seller)
        status = self.notifications.qualify_lead(request, buyer, seller, address).get("status")
        if status == "ADDRESS_TOO_SHORT":
            return "Delivery address ఇంకొంచెం పూర్తి వివరంగా పంపండి — House/Street, Area, Town, Pincode."
        if status == "WAITING_FINAL_CONFIRM":
            self._send_preorder_options(buyer, request_id, seller)
            return "✅ Address save అయింది. Final Order Summary పంపాను — Confirm Order, Sellerని అడగండి లేదా Direct Talk ఎంచుకోండి."
        if status == "LEAD_NOT_CONFIRMED":
            return "Seller confirmation లేదా Order Continue step ఇంకా complete కాలేదు."
        return "Delivery details save చేశాను."

    def _final_order(self, buyer: str, request_id: int, seller: str, accepted: bool) -> str:
        request = self.demands.get(request_id)
        if not request:
            return "ఆ PODX request దొరకలేదు."
        if accepted and self.deals is not None and not self.deals.is_confirmed(request_id, seller):
            return "💬 Seller doubt/clarification ఇంకా pendingలో ఉంది. Answer verify చేసి Deal OK చేసిన తర్వాత Confirm Order చేయండి."
        request = self._request_with_confirmed_deal(request, seller)
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
        if self.deals is not None and not self.deals.is_confirmed(request_id, seller):
            return "🔒 Contact share ముందు PODX Deal Discussion complete చేసి Deal OK confirm చేయాలి."
        status = self.notifications.share_contacts_after_confirmation(request, buyer, seller).get("status")
        return {
            "CONTACT_SHARED": "✅ Seller contact మీకు పంపాను. Sellerకి కూడా మీ contact పంపాను.",
            "ALREADY_SHARED": "ఈ match contact details ఇప్పటికే share అయ్యాయి.",
            "SELLER_NOT_CONFIRMED": "Seller ఇంకా confirm చేయలేదు.",
            "CONTACT_SHARE_PARTIAL_FAILURE": "Contact shareలో delivery సమస్య వచ్చింది.",
        }.get(status, "Direct Talk request save చేశాను.")

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
        return text.lower().strip() in cls.DECLINE_WORDS

    @staticmethod
    def _looks_like_deal_change(text: str) -> bool:
        lowered = text.casefold()
        return any(term in lowered for term in ("rate", "price", "quality", "quantity", "delivery", "pickup", "తగ్గ", "మార్చ", "క్వాలిటీ", "రేట్", "ధర", "డెలివరీ"))

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        return any(
            text.lower().strip().startswith(prefix)
            for prefix in (
                "buy_interested", "buy_not_interested", "seller_confirm", "seller_decline",
                "deal_confirm", "deal_change", "deal_question", "order_continue", "direct_talk", "final_confirm", "final_cancel", "interested",
                "not_interested", "confirm", "decline", "reject", "cancel", "contact", "done",
                "status", "menu", "help", "reset",
            )
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
