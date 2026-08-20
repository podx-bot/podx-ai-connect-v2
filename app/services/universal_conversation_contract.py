"""Universal Conversation Contract V1.

A deterministic, domain-neutral contract used by PODX to verify conversational
behaviour end-to-end before a release.  It intentionally does not know about
chicken, electricians, jobs or rides.  It reasons in lifecycle terms so the
same guarantees apply to every vertical and every channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Iterable


class UserTurnType(str, Enum):
    NEW = "NEW"
    UPDATE = "UPDATE"
    QUESTION = "QUESTION"
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    COMPLAINT = "COMPLAINT"
    CORRECTION = "CORRECTION"
    UNKNOWN = "UNKNOWN"


class ResponsePhase(str, Enum):
    MATCH = "MATCH"
    WAITING = "WAITING"
    NO_MATCH = "NO_MATCH"
    CANCELLED = "CANCELLED"
    ANSWER = "ANSWER"
    ACK = "ACK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ContractViolation:
    code: str
    detail: str


class UniversalConversationContract:
    """Pure contract evaluator shared by runtime guards and regression tests."""

    INTERNAL_MARKERS = (
        "seller-confirmed product profile",
        "seller-confirmed data",
        "resolved_meaning",
        "pending_action",
        "expected_reply_type",
        "active_flow",
        "state_json",
        "conversation os",
        "runtime",
    )
    CANCEL_MARKERS = ("cancel", "stop", "రద్దు", "వద్దు", "cancel it", "రద్దు చేయండి")
    COMPLAINT_MARKERS = ("complaint", "problem", "issue", "bad", "wrong", "సమస్య", "ఫిర్యాదు", "బాగోలేదు")
    CORRECTION_MARKERS = ("correction", "correct", "actually", "mistake", "తప్పు", "సరి", "మార్చు", "మార్చండి")
    QUESTION_MARKERS = ("?", "ఎంత", "రేట్", "price", "ధర", "ఉందా", "available", "ఎప్పుడు", "when", "where", "ఎక్కడ")
    UPDATE_MARKERS = (
        "కావాలి", "instead", "change", "make it", "update", "boneless", "బోన్లెస్",
        "fresh", "ఫ్రెష్", "kg", "కేజీ", "కిలో", "with", "without", "size", "color", "colour",
    )
    CONFIRM_MARKERS = ("yes", "ok", "okay", "confirm", "అవును", "సరే", "हाँ", "ठीक")

    MATCH_MARKERS = ("match దొరిక", "match found", "seller:", "provider:", "driver:", "worker:")
    WAIT_MARKERS = ("wait", "waiting", "pending", "confirmation", "availability", "వేచి", "confirm కోసం")
    NO_MATCH_MARKERS = ("no match", "match లేదు", "దొరకలేదు", "not found", "currently unavailable")
    CANCELLED_MARKERS = ("cancelled", "canceled", "రద్దు", "cancel చేశ")

    def classify_user_turn(self, message: str, state: dict | None = None) -> UserTurnType:
        text = self._clean(message)
        lower = text.casefold()
        if not text:
            return UserTurnType.UNKNOWN
        if self._contains_any(lower, self.CANCEL_MARKERS):
            return UserTurnType.CANCEL
        if self._contains_any(lower, self.COMPLAINT_MARKERS):
            return UserTurnType.COMPLAINT
        if self._contains_any(lower, self.CORRECTION_MARKERS):
            return UserTurnType.CORRECTION
        if self._contains_any(lower, self.QUESTION_MARKERS):
            return UserTurnType.QUESTION
        if self._contains_any(lower, self.CONFIRM_MARKERS) and self._expects_confirmation(state):
            return UserTurnType.CONFIRM
        if self._has_active_context(state) and self._contains_any(lower, self.UPDATE_MARKERS):
            return UserTurnType.UPDATE
        return UserTurnType.NEW

    def classify_response(self, reply: str) -> ResponsePhase:
        text = self._clean(reply).casefold()
        if not text:
            return ResponsePhase.UNKNOWN
        if self._contains_any(text, self.MATCH_MARKERS):
            return ResponsePhase.MATCH
        if self._contains_any(text, self.NO_MATCH_MARKERS):
            return ResponsePhase.NO_MATCH
        if self._contains_any(text, self.CANCELLED_MARKERS):
            return ResponsePhase.CANCELLED
        if self._contains_any(text, self.WAIT_MARKERS):
            return ResponsePhase.WAITING
        if "?" in text:
            return ResponsePhase.ANSWER
        return ResponsePhase.ACK

    def validate_turn(
        self,
        *,
        message: str,
        reply: str,
        state_before: dict | None = None,
        previous_reply: str | None = None,
        request_changed: bool | None = None,
    ) -> list[ContractViolation]:
        """Validate universal invariants without making domain-specific assumptions."""
        violations: list[ContractViolation] = []
        clean_reply = self._clean(reply)
        lower_reply = clean_reply.casefold()
        turn = self.classify_user_turn(message, state_before)
        phase = self.classify_response(clean_reply)
        previous_phase = self.classify_response(previous_reply or "")

        if not clean_reply:
            violations.append(ContractViolation("EMPTY_REPLY", "A user turn produced no customer-visible reply."))

        if self._contains_any(lower_reply, self.INTERNAL_MARKERS):
            violations.append(ContractViolation("INTERNAL_LANGUAGE_LEAK", "Internal runtime/state vocabulary reached the customer."))

        if previous_reply and self._clean(previous_reply).casefold() == lower_reply and phase == ResponsePhase.WAITING:
            violations.append(ContractViolation("DUPLICATE_PENDING_STATUS", "The same pending/waiting status was emitted again without new information."))

        if turn == UserTurnType.CANCEL and phase not in {ResponsePhase.CANCELLED, ResponsePhase.ACK}:
            violations.append(ContractViolation("CANCEL_NOT_HANDLED", "Cancellation did not move to a cancellation/acknowledgement response."))

        # Once a concrete match is already visible, the same unchanged request must
        # not silently regress to a generic waiting state. A true request update may
        # legitimately require re-matching, so callers can explicitly mark it changed.
        if previous_phase == ResponsePhase.MATCH and phase == ResponsePhase.WAITING and request_changed is False:
            violations.append(ContractViolation("MATCH_REGRESSED_TO_WAITING", "An unchanged matched request regressed to waiting."))

        if turn in {UserTurnType.UPDATE, UserTurnType.CORRECTION} and not self._has_active_context(state_before):
            violations.append(ContractViolation("UPDATE_WITHOUT_CONTEXT", "An update/correction was processed without an active conversation context."))

        return violations

    def release_matrix(self) -> tuple[str, ...]:
        """Required scenario families for every domain before a production release."""
        return (
            "new_request",
            "followup_update",
            "question_or_doubt",
            "correction",
            "complaint",
            "cancellation",
            "no_match",
            "match_found",
            "counterparty_reject",
            "timeout",
            "duplicate_inbound",
            "late_or_stale_event",
            "restart_and_resume",
            "telugu_english_mixed",
            "text_voice_equivalence",
            "internal_language_never_leaks",
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _contains_any(text: str, markers: Iterable[str]) -> bool:
        return any(str(marker).casefold() in text for marker in markers)

    @staticmethod
    def _has_active_context(state: dict | None) -> bool:
        state = state or {}
        return bool(state.get("active_entity") or state.get("active_flow") or (state.get("known_fields") or {}).get("request_text"))

    @staticmethod
    def _expects_confirmation(state: dict | None) -> bool:
        state = state or {}
        return str(state.get("expected_reply_type") or "").casefold() in {"yes_no", "confirmation"}
