"""PODX Conversation OS kernel.

Centralizes turn understanding before domain runtimes. The kernel does not own
commerce actions; it produces a stable interpretation envelope so every runtime
can reason from the previous PODX turn + current user turn + active state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class TurnKind(str, Enum):
    NEW_REQUEST = "NEW_REQUEST"
    UPDATE_EXISTING = "UPDATE_EXISTING"
    CLARIFICATION = "CLARIFICATION"
    QUESTION = "QUESTION"
    CONFIRMATION = "CONFIRMATION"
    CANCELLATION = "CANCELLATION"
    NEW_TOPIC = "NEW_TOPIC"
    UNKNOWN = "UNKNOWN"


@dataclass
class ConversationState:
    user_id: str
    goal: Optional[str] = None
    active_flow: Optional[str] = None
    active_entity: Optional[str] = None
    known_fields: Dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    pending_action: Optional[str] = None
    last_bot_message: Optional[str] = None
    last_bot_intent: Optional[str] = None
    expected_reply_type: Optional[str] = None
    last_user_message: Optional[str] = None


@dataclass
class TurnDecision:
    kind: TurnKind
    message: str
    state: ConversationState
    confidence: float
    resolved_meaning: Optional[str] = None
    next_action: Optional[str] = None
    should_clarify: bool = False


class ConversationKernel:
    """Small deterministic guardrail in front of specialized PODX brains.

    This first version intentionally handles the high-value conversational
    invariants deterministically. Model-backed semantic resolution can be added
    behind the same interface without changing downstream modules.
    """

    YES = {"yes", "yeah", "yep", "ok", "okay", "అవును", "సరే", "హా", "हाँ", "ठीक है"}
    NO = {"no", "nope", "వద్దు", "లేదు", "కాదు", "नहीं"}
    CANCEL = {"cancel", "stop", "రద్దు", "వద్దు", "cancel it", "రద్దు చేయండి"}
    QUESTION_MARKERS = ("?", "ఎంత", "రేట్", "price", "ధర", "ఉందా", "available", "ఎప్పుడు", "when", "where", "ఎక్కడ")

    # Strong markers communicate an actual modification/variant and therefore
    # keep the active conversation even in a longer sentence. Weak markers such
    # as quantity units or the generic Telugu word "కావాలి" are common in both
    # follow-ups and completely new requests, so they only imply continuation
    # for compact replies.
    STRONG_UPDATE_MARKERS = (
        "చేయండి", "మార్చండి", "మార్చు", "instead", "change", "make it", "update",
        "boneless", "బోన్లెస్", "skinless", "fresh", "ఫ్రెష్", "with bone", "without bone",
        "करो", "करें", "बदलो", "बदलें",
    )
    WEAK_UPDATE_MARKERS = (
        "కావాలి", "kg", "kgs", "కేజీ", "కిలో", "need", "want", "चाहिए", "चाहिये",
    )
    SHORT_FOLLOWUP_MAX_WORDS = 4

    def resolve(self, user_id: str, message: str, state: Optional[ConversationState] = None) -> TurnDecision:
        state = state or ConversationState(user_id=str(user_id))
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        state.last_user_message = clean

        if not clean:
            return TurnDecision(TurnKind.UNKNOWN, clean, state, 1.0, should_clarify=True)
        if lowered in self.CANCEL:
            return TurnDecision(TurnKind.CANCELLATION, clean, state, 0.99, "cancel active action", "cancel")
        if state.expected_reply_type in {"yes_no", "confirmation"} and lowered in self.YES | self.NO:
            meaning = "yes" if lowered in self.YES else "no"
            return TurnDecision(TurnKind.CONFIRMATION, clean, state, 0.99, meaning, state.pending_action)
        if any(marker in lowered for marker in self.QUESTION_MARKERS):
            return TurnDecision(TurnKind.QUESTION, clean, state, 0.90, clean, "answer_in_active_context")
        if state.active_entity and any(marker in lowered for marker in self.STRONG_UPDATE_MARKERS):
            return TurnDecision(TurnKind.UPDATE_EXISTING, clean, state, 0.90, clean, "merge_active_state")
        if (
            state.active_entity
            and len(clean.split()) <= self.SHORT_FOLLOWUP_MAX_WORDS
            and any(marker in lowered for marker in self.WEAK_UPDATE_MARKERS)
        ):
            return TurnDecision(TurnKind.UPDATE_EXISTING, clean, state, 0.86, clean, "merge_active_state")
        if state.expected_reply_type:
            return TurnDecision(TurnKind.CLARIFICATION, clean, state, 0.75, clean, "resolve_expected_reply")
        return TurnDecision(TurnKind.NEW_REQUEST, clean, state, 0.70, clean, "route_new_request")

    @staticmethod
    def validate_reply(decision: TurnDecision, reply: Optional[str]) -> Optional[str]:
        """Final response guard: empty replies never become user-visible output."""
        text = str(reply or "").strip()
        if not text:
            return None
        return text
