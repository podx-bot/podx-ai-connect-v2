"""Natural-language Event/Function RFQ extraction with low-cost keyword gating."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from google import genai


class EventIntentExtractor:
    EVENT_HINTS = (
        "event", "function", "marriage", "wedding", "birthday", "engagement", "reception",
        "పెళ్లి", "వివాహ", "ఫంక్షన్", "పుట్టినరోజు", "నిశ్చితార్థం", "రిసెప్షన్",
        "shaadi", "shadi", "कार्यक्रम", "शादी", "विवाह",
    )
    SERVICE_HINTS = (
        "catering", "food", "hall", "venue", "decoration", "decor", "photography", "photo", "video",
        "flowers", "sound", "dj", "transport", "bus", "car",
        "కేటరింగ్", "భోజనం", "హాల్", "డెకరేషన్", "ఫోటోగ్రఫీ", "పూలు", "సౌండ్", "డీజే", "ట్రాన్స్‌పోర్ట్",
    )

    def __init__(self, api_key: str = "", model: str = "gemini-3.6-flash", client: Any | None = None) -> None:
        self.api_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = str(model or os.getenv("GEMINI_VOICE_MODEL") or "gemini-3.6-flash").strip() or "gemini-3.6-flash"
        self._client = client or (genai.Client(api_key=self.api_key) if self.api_key else None)

    @classmethod
    def looks_like_event(cls, message: str) -> bool:
        text = " ".join(str(message or "").casefold().split())
        if not text:
            return False
        return any(word in text for word in cls.EVENT_HINTS) and any(word in text for word in cls.SERVICE_HINTS)

    def extract(self, message: str) -> dict[str, Any] | None:
        source = " ".join(str(message or "").strip().split())
        if not self.looks_like_event(source) or self._client is None:
            return None
        prompt = self._prompt(source)
        try:
            interaction = self._client.interactions.create(model=self.model, input=prompt, store=False)
            raw = str(getattr(interaction, "output_text", "") or "").strip()
            payload = self._json_object(raw)
        except Exception:
            return None
        if not bool(payload.get("is_event_request")):
            return None
        try:
            confidence = float(payload.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < 0.8:
            return None
        services = [str(x).strip().upper() for x in (payload.get("services") or []) if str(x).strip()]
        guest_count = self._positive_int(payload.get("guest_count"))
        location = self._clean(payload.get("location_text"))
        event_type = self._clean(payload.get("event_type")) or "Function"
        event_date = self._clean(payload.get("event_date"))
        missing = []
        if guest_count is None:
            missing.append("guest_count")
        if not location:
            missing.append("location")
        if not services:
            missing.append("services")
        return {
            "event_type": event_type,
            "guest_count": guest_count,
            "location_text": location,
            "services": services,
            "event_date": event_date,
            "missing": missing,
            "confidence": confidence,
        }

    @staticmethod
    def _prompt(source: str) -> str:
        return (
            "You extract one local Event/Function RFQ from a user's natural-language message. "
            "The user may speak Telugu, Hindi, English, mixed language or transliteration. "
            "Return exactly one JSON object, no markdown. Do not invent facts.\n"
            "Schema: {\"is_event_request\":true|false,\"event_type\":string|null,"
            "\"guest_count\":integer|null,\"location_text\":string|null,\"event_date\":string|null,"
            "\"services\":[\"CATERING|HALL|DECORATION|PHOTOGRAPHY|FLOWERS|SOUND|TRANSPORT\"],"
            "\"confidence\":number}.\n"
            "Only include services the user actually asks for. Normalize synonymous service words to the listed values. "
            "If this is not a function/event planning request, set is_event_request=false.\n"
            f"User message: {source}"
        )

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("No JSON object")
            data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("Expected object")
        return data

    @staticmethod
    def _clean(value: Any) -> str | None:
        text = " ".join(str(value or "").strip().split())
        return text or None

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None
