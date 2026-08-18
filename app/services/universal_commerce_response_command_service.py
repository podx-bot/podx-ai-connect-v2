"""Adapter that applies UniversalCommerceConversationEngine before legacy handlers."""
from __future__ import annotations

from typing import Optional

from app.services.universal_commerce_conversation_engine import UniversalCommerceConversationEngine
from app.services.universal_response_command_service import UniversalResponseCommandService


class UniversalCommerceResponseCommandService(UniversalResponseCommandService):
    """Drop-in replacement with state-first buyer/seller/doubt routing."""

    def __init__(self, *args, commerce_engine=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.commerce_engine = commerce_engine or UniversalCommerceConversationEngine()

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = self._clean(message)
        if not text:
            return None

        decision = self.commerce_engine.decide(
            sender_mobile,
            text,
            deals=self.deals,
            notifications=self.notification_repository,
            demands=self.demands,
        )

        # Commands/buttons remain owned by the stable legacy command parser.
        if decision.intent == "COMMAND":
            return super().process_text(sender_mobile, text)

        if decision.intent in {"BUYER_DOUBT_OR_CHANGE", "AUTO_BUYER_DOUBT"}:
            routed = self._route_buyer_doubt(sender_mobile, text, decision)
            if routed is not None:
                return routed

        if decision.intent == "SELLER_CLARIFICATION_REPLY":
            routed = self._route_seller_clarification(sender_mobile, text, decision)
            if routed is not None:
                return routed

        if decision.intent == "SELLER_COUNTER_QUESTION":
            routed = self._route_seller_counter_question(sender_mobile, text, decision)
            if routed is not None:
                return routed

        if decision.intent == "SELLER_DETAILS":
            routed = self._route_seller_details(sender_mobile, text, decision)
            if routed is not None:
                return routed

        # Keep all established registration/match/address/legacy behavior while
        # centralizing only the ambiguous commerce conversation states here.
        return super().process_text(sender_mobile, text)

    def _route_buyer_doubt(self, buyer: str, text: str, decision) -> Optional[str]:
        if self.deals is None or not decision.request_id or not decision.seller_user_id:
            return None
        request = self.demands.get(int(decision.request_id))
        if not request:
            return None
        seller = str(decision.seller_user_id)
        deal = self.deals.repository.get(int(decision.request_id), seller)
        if not deal or str(deal.get("buyer_user_id")) != str(buyer):
            return None

        # Natural final-stage questions auto-open the same safe relay loop that
        # the Seller Question button opens. The button is therefore optional.
        if str(deal.get("status") or "") != "WAITING_BUYER_CHANGE":
            if str(deal.get("status") or "") not in {"CONFIRMED", "WAITING_BUYER_CONFIRM"}:
                return None
            self.deals.repository.mark_waiting_buyer_change(int(decision.request_id), seller)

        return self.deals.consume_buyer_change(request, buyer, seller, text)

    def _route_seller_clarification(self, seller: str, text: str, decision) -> Optional[str]:
        """Relay an answer to the buyer before generic missing-field validation.

        A seller answering an active buyer doubt is not filling a fresh product
        form. The reply is attached to the pending clarification, merged into the
        deal facts when extractable, and returned to the buyer for re-confirm.
        """
        if self.deals is None or not decision.request_id or not decision.buyer_user_id:
            return None
        request_id = int(decision.request_id)
        buyer = str(decision.buyer_user_id)
        request = self.demands.get(request_id)
        if not request:
            return None
        deal = self.deals.repository.get(request_id, seller)
        if not deal or str(deal.get("status") or "") != "WAITING_SELLER_REVISION":
            return None

        parsed = self.deals._parse_details(request, text)
        if self.deals._category(request) == "PRODUCT" and self.deals.product_schema is not None:
            try:
                ai_details = self.deals.product_schema.extract_details(str(request.get("subject") or "item"), text)
                if isinstance(ai_details, dict):
                    parsed = self.deals._merge_detail_dicts(parsed, ai_details)
            except Exception:
                pass

        updated = self.deals.repository.save_seller_details(
            request_id,
            seller,
            parsed,
            text,
            revised=True,
        )
        if not updated:
            return None

        buyer_mobile = self.deals._mobile(buyer)
        question = str(deal.get("buyer_question") or "").strip()
        relay = "💬 Seller reply"
        if question:
            relay += f"\nమీ ప్రశ్న: {question}"
        relay += f"\nSeller: {text}"
        summary = self.deals._summary(request, updated)
        self.deals._send_buttons_or_text(
            buyer_mobile,
            relay + "\n\n" + summary + "\n\nఈ updated deal సరేనా?",
            [
                {"id": f"DEAL_CONFIRM {request_id} {seller}", "title": "✅ Deal OK"},
                {"id": f"DEAL_CHANGE {request_id} {seller}", "title": "💬 ఇంకా అడగండి"},
            ],
        )
        return "✅ Buyer clarificationకి మీ reply పంపాను. Buyer re-confirm కోసం wait చేస్తున్నాం."

    def _route_seller_counter_question(self, seller: str, text: str, decision) -> Optional[str]:
        """Allow natural buyer↔seller clarification ping-pong without contact leak."""
        if self.deals is None or not decision.request_id or not decision.buyer_user_id:
            return None
        request_id = int(decision.request_id)
        buyer = str(decision.buyer_user_id)
        deal = self.deals.repository.get(request_id, seller)
        if not deal or str(deal.get("status") or "") != "WAITING_SELLER_REVISION":
            return None

        buyer_mobile = self.deals._mobile(buyer)
        self.deals.repository.mark_waiting_buyer_change(request_id, seller)
        self.deals.whatsapp.send_text_message(
            buyer_mobile,
            f"💬 Seller clarification:\n{text}\n\nమీ answer మీ మాటల్లో reply చేయండి. PODX privateగా sellerకి relay చేస్తుంది.",
        )
        return "✅ మీ clarification buyerకి privateగా పంపాను. Buyer reply వచ్చిన తర్వాత PODX మీకు relay చేస్తుంది."

    def _route_seller_details(self, seller: str, text: str, decision) -> Optional[str]:
        if self.deals is None or not decision.request_id or not decision.buyer_user_id:
            return None
        request = self.demands.get(int(decision.request_id))
        if not request:
            return None
        return self.deals.consume_seller_text(
            request,
            str(decision.buyer_user_id),
            seller,
            text,
        )
