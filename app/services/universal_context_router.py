"""Universal conversation-context isolation for PODX deal routing.

This module is product-agnostic.  It prevents an unfinished deal from
swallowing a new product/service intent while still allowing short follow-up
messages that only contain deal attributes such as price, quantity or pickup.

An optional AI semantic classifier can be supplied.  When available it is the
source of truth; the lexical fallback exists so routing remains safe when the
AI provider is unavailable.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional


class UniversalContextRouter:
    DETAIL_WORDS = {
        "price", "rate", "quality", "type", "variant", "brand", "model", "size",
        "fresh", "premium", "new", "used", "sealed", "original", "available",
        "today", "tomorrow", "delivery", "pickup", "pick", "only", "per",
        "kg", "kgs", "kilogram", "kilograms", "g", "gm", "gms", "gram", "grams",
        "l", "ltr", "litre", "litres", "liter", "liters", "ml",
        "piece", "pieces", "pc", "pcs", "unit", "units", "bag", "bags",
        "pack", "packs", "packet", "packets", "box", "boxes",
        "rs", "inr", "rupees", "need", "want", "have", "sell", "selling",
        "buy", "buying", "good", "best",
    }

    def __init__(
        self,
        semantic_classifier: Optional[Callable[[dict[str, Any], str], Any]] = None,
    ) -> None:
        self.semantic_classifier = semantic_classifier

    @staticmethod
    def _tokens(value: Any) -> set[str]:
        return {
            token.casefold()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", str(value or ""))
        }

    def introduces_new_subject(self, request: dict[str, Any], text: str) -> bool:
        """Return True when a message is semantically a new subject/request.

        The AI hook may return a bool, or a mapping containing
        ``new_subject`` / ``same_context``.  Any provider error falls back to a
        conservative generic lexical check; no product names are hard-coded.
        """
        if callable(self.semantic_classifier):
            try:
                verdict = self.semantic_classifier(dict(request or {}), str(text or ""))
                if isinstance(verdict, bool):
                    return verdict
                if isinstance(verdict, dict):
                    if "new_subject" in verdict:
                        return bool(verdict["new_subject"])
                    if "same_context" in verdict:
                        return not bool(verdict["same_context"])
            except Exception:
                pass

        subject_tokens = self._tokens((request or {}).get("subject"))
        message_tokens = self._tokens(text)
        if not subject_tokens or not message_tokens:
            return False

        # Explicit mention of the current item strongly means same context.
        if subject_tokens & message_tokens:
            return False

        candidates = message_tokens - self.DETAIL_WORDS
        # If the message only contains deal attributes/numbers, keep the
        # current deal.  If it introduces meaningful new lexical content while
        # omitting the current subject, let the normal AI intent pipeline route
        # it as a new request instead of mutating the old deal.
        return bool(candidates)

    def should_consume_as_deal_followup(self, request: dict[str, Any], text: str) -> bool:
        return not self.introduces_new_subject(request, text)
