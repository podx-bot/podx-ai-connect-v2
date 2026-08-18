"""State-first universal commerce conversation engine.

This module centralizes message intent decisions for buyer/seller commerce flows.
It is intentionally product-agnostic: product schemas provide facts/fields, while
this engine decides what a human message means in the current deal state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.services.universal_human_behaviour_brain import UniversalHumanBehaviourBrain


@dataclass(frozen=True)
class ConversationDecision:
    intent: str
    confidence: float
    reason: str
    request_id: Optional[int] = None
    seller_user_id: Optional[str] = None
    buyer_user_id: Optional[str] = None
    behaviour: Optional[str] = None
    recommended_action: Optional[str] = None


class UniversalCommerceConversationEngine:
    """Deterministic state-first router for commerce conversations.

    Priority order:
    1. explicit button/command
    2. explicit waiting state (buyer doubt/change, seller revision, address)
    3. pre-order natural question detection
    4. negotiation/change detection
    5. seller factual detail reply
    6. generic human behaviour

    This prevents a multi-role user's message from being consumed by the wrong
    deal merely because they are also a seller/buyer elsewhere.
    """

    QUESTION_MARKERS = {
        "?", "ఎందుకు", "ఎలా", "ఎప్పుడు", "ఎక్కడ", "ఉందా", "ఉంటుందా", "చేస్తారా",
        "కావాలా", "వస్తుందా", "ఇస్తారా", "can", "does", "is there", "how", "when",
        "where", "what", "why", "warranty", "guarantee", "installation", "bill",
        "invoice", "expiry", "return", "replacement", "delivery time", "service",
        "demo", "test", "working", "original", "genuine", "brand", "model",
        "accessories", "free", "charges", "charge", "available?",
    }

    NEGOTIATION_MARKERS = {
        "reduce", "less", "discount", "best price", "last price", "change", "instead",
        "rate", "price", "ధర", "రేట్", "తగ్గ", "డిస్కౌంట్", "మార్చ", "క్వాలిటీ",
        "quality", "quantity", "delivery", "pickup", "variant", "size", "color",
    }

    FACT_MARKERS = {
        "available", "delivery", "pickup", "new", "used", "working", "model", "brand",
        "warranty", "guarantee", "included", "with", "without", "per kg", "per bag",
        "per unit", "₹", "rs", "rate", "price", "stock", "today", "tomorrow",
    }

    COMMAND_PREFIXES = (
        "buy_interested", "buy_not_interested", "seller_confirm", "seller_decline",
        "deal_confirm", "deal_change", "deal_question", "order_continue", "direct_talk",
        "final_confirm", "final_cancel", "interested", "not_interested", "confirm",
        "decline", "reject", "cancel", "contact", "done", "status", "menu", "help", "reset",
    )

    def __init__(self, behaviour_brain=None) -> None:
        self.behaviour_brain = behaviour_brain or UniversalHumanBehaviourBrain()

    def decide(self, sender: str, text: str, *, deals=None, notifications=None, demands=None) -> ConversationDecision:
        clean = self._clean(text)
        if not clean:
            return ConversationDecision("EMPTY", 1.0, "empty message")

        if self._looks_like_command(clean):
            return ConversationDecision("COMMAND", 1.0, "explicit command/button payload")

        # Explicit conversational state wins over every semantic guess.
        if deals is not None:
            buyer_change = self._safe_call(deals, "pending_for_buyer_change", sender)
            if buyer_change:
                return self._decision_from_deal("BUYER_DOUBT_OR_CHANGE", 1.0, "buyer is explicitly waiting to send a doubt/change", buyer_change)

        # Final-order state: a natural question must become a seller doubt even
        # if the user did not press the Seller Question button first.
        if notifications is not None:
            final_wait = self._safe_call(notifications, "latest_waiting_final_confirm_for_buyer", sender)
            if final_wait and self.is_question(clean):
                return ConversationDecision(
                    "AUTO_BUYER_DOUBT",
                    0.98,
                    "buyer is at final confirm and message is a natural product/order question",
                    request_id=self._to_int(final_wait.get("request_id")),
                    seller_user_id=str(final_wait.get("responder_user_id") or "") or None,
                    buyer_user_id=str(final_wait.get("requester_user_id") or sender),
                    behaviour="ASK",
                    recommended_action="ROUTE_TO_COUNTERPARTY",
                )

        if deals is not None:
            seller_pending = self._safe_call(deals, "pending_for_seller", sender)
            if seller_pending:
                status = str(seller_pending.get("status") or "")
                if status == "WAITING_SELLER_REVISION":
                    behaviour = self.behaviour_brain.classify(clean, pending_state=status)
                    if behaviour.behaviour == "COUNTER_QUESTION" and not self.looks_like_factual_answer(clean):
                        return self._decision_from_deal(
                            "SELLER_COUNTER_QUESTION",
                            0.99,
                            "seller is replying to a buyer clarification with a counter-question",
                            seller_pending,
                            behaviour="COUNTER_QUESTION",
                            recommended_action="ROUTE_TO_COUNTERPARTY",
                        )
                    return self._decision_from_deal(
                        "SELLER_CLARIFICATION_REPLY",
                        0.99,
                        "seller reply belongs to the active buyer clarification before missing-field logic",
                        seller_pending,
                        behaviour="INFORM_OR_ANSWER",
                        recommended_action="ROUTE_TO_COUNTERPARTY",
                    )

                # If this sender is also clearly asking a question, do not steal
                # it as seller details. Seller details should normally be factual.
                if self.is_question(clean) and not self.looks_like_factual_answer(clean):
                    return ConversationDecision("UNRESOLVED_QUESTION", 0.75, "question conflicts with pending seller-detail state", behaviour="ASK", recommended_action="AUTO_RESOLVE")
                return self._decision_from_deal("SELLER_DETAILS", 0.97, "seller is explicitly waiting to provide deal facts", seller_pending, behaviour="INFORM_OR_ANSWER", recommended_action="ASK_MISSING_ONLY")

            buyer_summary = self._safe_call(deals, "pending_for_buyer_summary", sender)
            if buyer_summary:
                if self.is_question(clean):
                    return self._decision_from_deal("AUTO_BUYER_DOUBT", 0.95, "buyer has an active deal summary and asked a natural question", buyer_summary, behaviour="ASK", recommended_action="ROUTE_TO_COUNTERPARTY")
                if self.is_negotiation(clean):
                    return self._decision_from_deal("BUYER_DOUBT_OR_CHANGE", 0.93, "buyer requested a deal change/negotiation", buyer_summary, behaviour="NEGOTIATE", recommended_action="ROUTE_TO_COUNTERPARTY")

        behaviour = self.behaviour_brain.classify(clean)
        plan = self.behaviour_brain.next_action(behaviour.behaviour)
        if self.is_question(clean):
            return ConversationDecision("GENERIC_COMMERCE_QUESTION", 0.82, "natural-language commerce question", behaviour=behaviour.behaviour, recommended_action=plan.action)
        if self.is_negotiation(clean):
            return ConversationDecision("GENERIC_NEGOTIATION", 0.80, "natural-language negotiation/change", behaviour=behaviour.behaviour, recommended_action=plan.action)
        if self.looks_like_factual_answer(clean):
            return ConversationDecision("GENERIC_FACTS", 0.72, "message contains factual commerce attributes", behaviour=behaviour.behaviour, recommended_action=plan.action)
        return ConversationDecision("GENERIC_TEXT", 0.50, "no strong commerce-state signal", behaviour=behaviour.behaviour, recommended_action=plan.action)

    def is_question(self, text: str) -> bool:
        low = self._clean(text).casefold()
        if "?" in low:
            return True
        return any(marker in low for marker in self.QUESTION_MARKERS if marker != "?")

    def is_negotiation(self, text: str) -> bool:
        low = self._clean(text).casefold()
        return any(marker in low for marker in self.NEGOTIATION_MARKERS)

    def looks_like_factual_answer(self, text: str) -> bool:
        low = self._clean(text).casefold()
        has_number = bool(re.search(r"\d", low))
        has_fact_word = any(marker in low for marker in self.FACT_MARKERS)
        # Questions with only a fact keyword are not factual answers.
        return (has_number or has_fact_word) and not (self.is_question(low) and not has_number)

    @classmethod
    def _looks_like_command(cls, text: str) -> bool:
        low = cls._clean(text).casefold()
        return any(low.startswith(prefix) for prefix in cls.COMMAND_PREFIXES)

    @staticmethod
    def _safe_call(obj: Any, name: str, *args):
        fn = getattr(obj, name, None)
        if not callable(fn):
            return None
        try:
            return fn(*args)
        except Exception:
            return None

    @classmethod
    def _decision_from_deal(
        cls,
        intent: str,
        confidence: float,
        reason: str,
        deal: dict,
        *,
        behaviour: Optional[str] = None,
        recommended_action: Optional[str] = None,
    ) -> ConversationDecision:
        return ConversationDecision(
            intent,
            confidence,
            reason,
            request_id=cls._to_int(deal.get("request_id")),
            seller_user_id=str(deal.get("seller_user_id") or "") or None,
            buyer_user_id=str(deal.get("buyer_user_id") or "") or None,
            behaviour=behaviour,
            recommended_action=recommended_action,
        )

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())
