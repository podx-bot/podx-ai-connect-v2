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
