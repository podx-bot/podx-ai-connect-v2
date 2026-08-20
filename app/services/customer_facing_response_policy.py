"""Final customer-facing response guard for every conversational domain.

This layer sits outside Conversation OS. Domain runtimes may use operational
language internally, but WhatsApp/app/web users should receive short, natural,
context-aware language only.
"""
from __future__ import annotations

import re
from typing import Any


class CustomerFacingResponsePolicy:
    INTERNAL_MARKERS = (
        "seller-confirmed product profile",
        "seller-confirmed data",
        "final confirm",
        "resolved_meaning",
        "pending_action",
        "expected_reply_type",
        "active_flow",
        "conversation os",
        "runtime",
        "state_json",
    )
    UPDATE_HINTS = (
        "కావాలి", "వద్దు", "మార్చు", "change", "instead", "want", "need",
        "boneless", "బోన్లెస్", "with", "without", "size", "color", "colour",
        "quantity", "kg", "కేజీ",
    )

    def __init__(self, delegate: Any, ledger_repository: Any = None) -> None:
        self.delegate = delegate
        self.ledger_repository = ledger_repository

    def process(self, sender_mobile: str, message: str) -> str:
        reply = self.delegate.process(sender_mobile=sender_mobile, message=message)
        return self.render(sender_mobile, message, reply)

    def render(self, sender_mobile: str, message: str, reply: Any) -> str:
        text = str(reply or "").strip()
        if not text:
            return text
        lowered = text.casefold()
        if not any(marker in lowered for marker in self.INTERNAL_MARKERS):
            return text

        state = self._state(sender_mobile)
        entity = str(state.get("active_entity") or "").strip()
        fields = state.get("known_fields") or {}
        quantity = self._quantity(fields)
        update = any(hint in str(message or "").casefold() for hint in self.UPDATE_HINTS)

        if update:
            context = " ".join(part for part in (quantity, entity) if part).strip()
            if context:
                return f"సరే 👍 {context} requestలో మీరు చెప్పిన కొత్త వివరాన్ని గమనించాను. దానికి సరిపోయే optionని చూస్తున్నాను."
            return "సరే 👍 మీరు చెప్పిన కొత్త వివరాన్ని గమనించాను. దానికి సరిపోయే optionని చూస్తున్నాను."

        # Never leak implementation/state vocabulary. Preserve the useful idea:
        # PODX does not invent facts and will verify missing seller information.
        if self._looks_telugu(message):
            return "ఈ వివరానికి ఇంకా ఖచ్చితమైన సమాచారం లేదు. ఊహించి చెప్పకుండా సరైన సమాచారం confirm చేసి చెప్తాను."
        return "I don't have a confirmed answer for that detail yet. I’ll verify it rather than guess."

    def _state(self, sender_mobile: str) -> dict:
        if self.ledger_repository is None:
            return {}
        try:
            return self.ledger_repository.load_state(sender_mobile) or {}
        except Exception:
            return {}

    @staticmethod
    def _quantity(fields: dict) -> str:
        quantity = fields.get("quantity")
        if quantity in (None, ""):
            return ""
        unit = str(fields.get("unit") or "").strip()
        value = str(quantity).strip()
        try:
            number = float(value)
            value = str(int(number)) if number.is_integer() else str(number)
        except (TypeError, ValueError):
            pass
        return f"{value} {unit}".strip()

    @staticmethod
    def _looks_telugu(text: str) -> bool:
        return bool(re.search(r"[\u0C00-\u0C7F]", str(text or "")))
