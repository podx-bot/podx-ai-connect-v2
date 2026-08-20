"""Conversation topic continuity resolver for PODX Conversation OS."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict


class ConversationTopicResolver:
    NEW_TOPIC_MARKERS = (
        "also need", "i also need", "ఇంకా కావాలి", "కూడా కావాలి", "మరొకటి",
        "another", "instead of that", "వేరే", "new request",
    )
    FOLLOWUP_MARKERS = (
        "boneless", "బోన్లెస్", "fresh", "ఫ్రెష్", "skinless", "with bone",
        "without bone", "kg", "kgs", "కేజీ", "కిలో", "rate", "price", "రేట్",
        "ధర", "delivery", "pickup", "today", "tomorrow", "ఈరోజు", "రేపు",
    )

    def resolve(self, active_entity: str | None, message: str, extracted: Dict[str, Any] | None = None) -> str:
        clean = self._normalize(message)
        active = self._normalize(active_entity)
        extracted = extracted or {}
        extracted_subject = self._normalize(extracted.get("subject"))

        if not active:
            return "NEW_TOPIC"
        if extracted_subject:
            if self._similar(active, extracted_subject) >= 0.70:
                return "CONTINUE"
            if self._contains_subject(active, clean):
                return "CONTINUE"
            return "NEW_TOPIC"
        if any(marker in clean for marker in self.FOLLOWUP_MARKERS):
            return "CONTINUE"
        if self._contains_subject(active, clean):
            return "CONTINUE"
        if any(marker in clean for marker in self.NEW_TOPIC_MARKERS):
            return "POSSIBLE_NEW_TOPIC"
        if len(clean.split()) <= 4:
            return "AMBIGUOUS_FOLLOWUP"
        return "POSSIBLE_NEW_TOPIC"

    @classmethod
    def _contains_subject(cls, subject: str, text: str) -> bool:
        if not subject or not text:
            return False
        return subject in text or text in subject

    @classmethod
    def _similar(cls, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0
        la, lb = set(left.split()), set(right.split())
        union = la | lb
        jaccard = len(la & lb) / len(union) if union else 0.0
        return max(jaccard, SequenceMatcher(None, left, right).ratio())

    @staticmethod
    def _normalize(value: Any) -> str:
        text = str(value or "").casefold().strip()
        text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
        return " ".join(text.split())
