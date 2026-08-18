"""Universal human-behaviour intelligence for PODX conversational flows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BehaviourDecision:
    behaviour: str
    confidence: float
    reason: str
    domain: str = "GENERIC"


@dataclass(frozen=True)
class NextAction:
    action: str
    reason: str
    ask_fields: tuple[str, ...] = ()


class UniversalHumanBehaviourBrain:
    """Classify natural seeker/provider behaviour before form-field logic."""

    DEFAULT_MAX_AUTO_ATTEMPTS = 2

    FLOW_PROFILES = {
        "JOBS": ("role", "location", "experience", "salary", "availability"),
        "COMMERCE": ("item", "variant", "price", "availability", "fulfilment"),
        "SERVICES": ("problem_or_scope", "location", "preferred_time", "price"),
        "FREELANCE": ("scope", "deliverables", "budget", "deadline", "skills"),
        "MOBILITY_TAXI": ("pickup", "destination", "vehicle", "time", "fare"),
        "MOBILITY_POOL": ("from", "to", "date_time", "vehicle", "seats", "share_amount"),
        "FOOD": ("item", "variant", "quantity", "delivery_location"),
        "DELIVERY": ("pickup", "drop", "item_type", "vehicle", "time"),
        "HEALTHCARE": ("need_or_specialty", "location", "preferred_time"),
        "PROPERTY": ("buy_rent_sell", "location", "budget", "property_type"),
        "TRAVEL": ("destination", "date", "people", "budget"),
        "B2B_RFQ": ("requirement", "quantity", "specification", "location", "timeline"),
        "GENERIC": ("need", "location", "time"),
    }

    MARKERS = {
        "ACCEPT": ("ok", "okay", "agree", "accepted", "సరే", "ఓకే"),
        "REJECT": ("reject", "not interested", "వద్దు", "నచ్చలేదు"),
        "NEGOTIATE": ("reduce", "discount", "best price", "last price", "తగ్గ", "డిస్కౌంట్", "రేట్"),
        "SCHEDULE": ("book", "schedule", "today", "tomorrow", "slot", "ఈరోజు", "రేపు"),
        "RESCHEDULE": ("reschedule", "change time", "later", "మరో టైమ్", "సమయం మార్చ"),
        "CANCEL": ("cancel", "stop", "రద్దు", "క్యాన్సిల్"),
        "COMPARE": ("compare", "which is better", "best one", "ఏది మంచిది"),
        "COMPLAINT": ("problem", "issue", "not working", "complaint", "సమస్య", "పని చేయడం లేదు"),
        "TRUST_SAFETY": ("verified", "safe", "genuine", "original", "trust", "సేఫ్", "నిజమా"),
        "PAYMENT": ("payment", "pay", "upi", "refund", "cash", "చెల్లింపు", "రిఫండ్"),
        "DELIVERY": ("delivery", "pickup", "shipping", "డెలివరీ", "పికప్"),
        "AVAILABILITY": ("available", "stock", "slot", "ఉందా", "అందుబాటులో"),
        "CONTACT": ("contact", "phone", "call", "number", "direct talk", "నంబర్", "కాంటాక్ట్"),
        "URGENT": ("urgent", "now", "immediately", "asap", "ఇప్పుడే", "అర్జెంట్", "వెంటనే"),
    }

    QUESTION_WORDS = ("?", "how", "what", "when", "where", "why", "can", "does", "is there", "ఎలా", "ఏంటి", "ఎప్పుడు", "ఎక్కడ", "ఎందుకు", "ఉందా")

    def classify(self, text: str, *, domain_hint: Optional[str] = None, pending_state: Optional[str] = None) -> BehaviourDecision:
        low = self._clean(text).casefold()
        domain = self._domain(domain_hint)
        if not low:
            return BehaviourDecision("EMPTY", 1.0, "empty message", domain)
        if pending_state and "SELLER" in str(pending_state).upper() and self._is_question(low):
            return BehaviourDecision("COUNTER_QUESTION", 0.96, "provider asked a question inside active clarification", domain)
        for behaviour in ("CANCEL", "RESCHEDULE", "REJECT", "ACCEPT", "NEGOTIATE", "COMPLAINT", "TRUST_SAFETY", "PAYMENT", "CONTACT", "URGENT", "COMPARE", "SCHEDULE", "DELIVERY", "AVAILABILITY"):
            if any(marker in low for marker in self.MARKERS[behaviour]):
                return BehaviourDecision(behaviour, 0.90, f"matched natural {behaviour.lower()} behaviour", domain)
        if self._is_question(low):
            return BehaviourDecision("ASK", 0.86, "natural question", domain)
        return BehaviourDecision("INFORM_OR_ANSWER", 0.68, "factual or free-form response", domain)

    def next_action(self, behaviour: str, *, missing_fields: Optional[list[str]] = None, auto_attempts: int = 0, counterparty_available: bool = False, human_support_available: bool = True) -> NextAction:
        missing = tuple(str(x) for x in (missing_fields or []) if str(x).strip())
        if behaviour == "CONTACT" and counterparty_available:
            return NextAction("OFFER_DIRECT_CONTACT", "user explicitly requested counterpart contact")
        if auto_attempts >= self.DEFAULT_MAX_AUTO_ATTEMPTS:
            if counterparty_available:
                return NextAction("OFFER_DIRECT_CONTACT", "automatic resolution attempts exhausted")
            if human_support_available:
                return NextAction("ESCALATE_HUMAN_SUPPORT", "automatic resolution attempts exhausted")
            return NextAction("CAPTURE_UNRESOLVED", "queue unresolved need for later resolution")
        if behaviour in {"ASK", "COMPLAINT", "PAYMENT", "TRUST_SAFETY", "AVAILABILITY"}:
            return NextAction("AUTO_RESOLVE", "answer from known data or AI first")
        if behaviour in {"NEGOTIATE", "COUNTER_QUESTION"}:
            return NextAction("ROUTE_TO_COUNTERPARTY", "counterpart must respond")
        if behaviour in {"ACCEPT", "REJECT", "CANCEL", "SCHEDULE", "RESCHEDULE"}:
            return NextAction("APPLY_STATE_TRANSITION", "message changes workflow state")
        if missing:
            return NextAction("ASK_MISSING_ONLY", "ask only unresolved essential facts", missing[:3])
        return NextAction("CONTINUE_MATCH_OR_COMPLETE", "enough information to continue")

    def required_fields(self, domain: Optional[str]) -> tuple[str, ...]:
        return self.FLOW_PROFILES.get(self._domain(domain), self.FLOW_PROFILES["GENERIC"])

    @classmethod
    def _is_question(cls, text: str) -> bool:
        return any(marker in text for marker in cls.QUESTION_WORDS)

    @classmethod
    def _domain(cls, value: Optional[str]) -> str:
        raw = str(value or "GENERIC").strip().upper().replace(" ", "_")
        aliases = {"JOB": "JOBS", "WORK": "JOBS", "PRODUCT": "COMMERCE", "PRODUCTS": "COMMERCE", "SERVICE": "SERVICES", "RIDE": "MOBILITY_TAXI", "TAXI": "MOBILITY_TAXI", "CARPOOL": "MOBILITY_POOL", "BIKEPOOL": "MOBILITY_POOL", "RFQ": "B2B_RFQ"}
        return aliases.get(raw, raw if raw in cls.FLOW_PROFILES else "GENERIC")

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(str(value or "").strip().split())
