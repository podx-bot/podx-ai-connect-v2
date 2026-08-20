"""Universal conversation-context isolation for PODX deal routing.

This module is product-agnostic. It prevents an unfinished deal from
swallowing a new product/service intent while still allowing short follow-up
messages that only contain deal attributes such as price, quantity or pickup.

An optional AI semantic classifier can be supplied. When available it is the
source of truth; the lexical fallback exists so routing remains safe when the
AI provider is unavailable.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Optional


class UniversalContextRouter:
    DETAIL_WORDS = {
        "price", "rate", "quality", "type", "variant", "brand", "model", "size",
        "fresh", "premium", "new", "used", "sealed", "original", "available",
        "skinless", "boneless", "with", "without", "change", "update", "instead",
        "today", "tomorrow", "delivery", "pickup", "pick", "only", "per",
        "kg", "kgs", "kilogram", "kilograms", "g", "gm", "gms", "gram", "grams",
        "l", "ltr", "litre", "litres", "liter", "liters", "ml",
        "piece", "pieces", "pc", "pcs", "unit", "units", "bag", "bags",
        "pack", "packs", "packet", "packets", "box", "boxes",
        "rs", "inr", "rupees", "need", "want", "have", "sell", "selling",
        "buy", "buying", "good", "best",
        # Telugu/Hindi conversational detail/change words. These are deliberately
        # domain-neutral where possible: they describe quantity, timing,
        # fulfilment, modification or intent rather than naming a subject.
        "కావాలి", "ఉంది", "ఉందా", "ఇవ్వండి", "తీసుకుంటాను", "చేయండి", "మార్చండి", "మార్చు",
        "కేజీ", "కేజీలు", "కేజీల", "కిలో", "కిలోలు", "గ్రాము", "గ్రాములు",
        "లీటర్", "లీటర్లు", "పీస్", "పీసులు", "ప్యాక్", "ప్యాకెట్లు", "బ్యాగ్", "బ్యాగులు",
        "డెలివరీ", "పికప్", "ఈరోజు", "రేపు", "ధర", "రేట్", "క్వాలిటీ",
        "चाहिए", "चाहिये", "लेना", "देना", "करो", "करें", "बदलो", "बदलें",
        "किलो", "किलोग्राम", "ग्राम", "लीटर", "पीस", "पैक", "बैग",
        "डिलीवरी", "पिकअप", "आज", "कल", "कीमत", "रेट",
    }
    PACKAGE_WORDS = {
        "bag", "bags", "pack", "packs", "packet", "packets", "box", "boxes",
        "piece", "pieces", "pc", "pcs", "unit", "units",
        "కేజీ", "కేజీలు", "కేజీల", "కిలో", "కిలోలు", "పీస్", "పీసులు", "ప్యాక్",
        "ప్యాకెట్లు", "బ్యాగ్", "బ్యాగులు",
        "किलो", "किलोग्राम", "पीस", "पैक", "बैग",
    }
    QUESTION_MARKERS = (
        "?", "how", "what", "which", "why", "when", "where", "price?", "rate?",
        "ఎంత", "ఏంటి", "ఏమిటి", "ఉందా", "దొరుకుతుందా", "కావాలా", "కొనాలా",
        "क्या", "कितना", "कौन", "कहाँ", "कब", "कैसे",
    )

    def __init__(
        self,
        semantic_classifier: Optional[Callable[[dict[str, Any], str], Any]] = None,
    ) -> None:
        self.semantic_classifier = semantic_classifier

    @staticmethod
    def _tokens(value: Any) -> set[str]:
        """Return Unicode-aware word tokens while preserving Indic combining marks.

        Python ``re`` word-boundary patterns split Telugu/Hindi grapheme clusters
        around combining marks, and the previous ASCII-only tokenizer ignored them
        entirely. A small category-based scanner keeps letters + marks together so
        multilingual requests participate in the same context-isolation rules.
        Numeric-only chunks are intentionally excluded.
        """
        tokens: set[str] = set()
        current: list[str] = []

        def flush() -> None:
            if not current:
                return
            token = "".join(current).strip("-").casefold()
            current.clear()
            if not token:
                return
            if any(unicodedata.category(char).startswith("L") for char in token):
                tokens.add(token)

        for char in str(value or ""):
            category = unicodedata.category(char)
            if category[:1] in {"L", "M", "N"} or char == "-":
                current.append(char)
            else:
                flush()
        flush()
        return tokens

    @staticmethod
    def _subject_is_mentioned(subject_tokens: set[str], message_tokens: set[str]) -> bool:
        if subject_tokens & message_tokens:
            return True
        return any(
            subject in message or message in subject
            for subject in subject_tokens
            for message in message_tokens
            if len(subject) >= 4 and len(message) >= 4
        )

    @classmethod
    def _looks_like_question(cls, text: str) -> bool:
        lowered = str(text or "").casefold()
        return any(marker in lowered for marker in cls.QUESTION_MARKERS)

    def introduces_new_subject(self, request: dict[str, Any], text: str) -> bool:
        """Return True when a message is semantically a new subject/request."""
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

        raw_text = str(text or "")
        subject_tokens = self._tokens((request or {}).get("subject"))
        message_tokens = self._tokens(raw_text)
        if not subject_tokens or not message_tokens:
            return False

        if self._subject_is_mentioned(subject_tokens, message_tokens):
            return False

        # A product-detail question such as "motor warranty ఎంత?" should stay
        # attached to the current matched product even if the question contains
        # an attribute noun that is not present in the product title. New listing
        # or request assertions continue through the generic subject detector.
        if self._looks_like_question(raw_text):
            return False

        candidates = message_tokens - self.DETAIL_WORDS
        if not candidates:
            return False

        if len(candidates) >= 2:
            return True

        has_number = bool(re.search(r"\d", raw_text))
        has_package = bool(message_tokens & self.PACKAGE_WORDS)
        return has_number and has_package

    def should_consume_as_deal_followup(self, request: dict[str, Any], text: str) -> bool:
        return not self.introduces_new_subject(request, text)
