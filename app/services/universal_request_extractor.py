from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from google import genai


VALID_SIDES = {"NEED", "OFFER"}
VALID_DOMAINS = {"WORK", "WORKERS", "SERVICE", "PRODUCT", "OTHER"}


@dataclass
class UniversalRequest:
    side: str
    domain: str
    subject: str
    quantity: float | None = None
    unit: str | None = None
    price: float | None = None
    currency: str | None = None
    when_text: str | None = None
    location_text: str | None = None
    location_required: bool = True
    constraints: list[str] = field(default_factory=list)
    confidence: float = 0.0
    source_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UniversalRequestExtractor:
    """Convert arbitrary natural-language PODX messages into one universal record.

    The extractor intentionally does not depend on a fixed category list. The model
    must preserve the user's free-form subject (profession, task, service, product,
    material, or future category) and only normalize the commercial relationship:
    NEED versus OFFER and a broad domain.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "gemini-3.6-flash",
        client: Any | None = None,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip() or "gemini-3.6-flash"
        self._client = client or (genai.Client(api_key=self.api_key) if self.api_key else None)

    def extract(self, message: str) -> dict[str, Any]:
        source_text = " ".join(str(message or "").strip().split())
        if not source_text:
            return {
                "success": False,
                "status": "EMPTY_MESSAGE",
                "request": None,
            }
        if self._client is None:
            return {
                "success": False,
                "status": "AI_NOT_CONFIGURED",
                "request": None,
            }

        prompt = self._build_prompt(source_text)
        try:
            interaction = self._client.interactions.create(
                model=self.model,
                input=prompt,
                store=False,
            )
            raw = str(getattr(interaction, "output_text", "") or "").strip()
            payload = self._parse_json_object(raw)
            request = self._normalize_payload(payload, source_text=source_text)
            return {
                "success": True,
                "status": "EXTRACTED",
                "request": request.to_dict(),
                "raw_output": raw,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "EXTRACTION_ERROR",
                "request": None,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            }

    @staticmethod
    def _build_prompt(source_text: str) -> str:
        return (
            "You are the universal understanding layer for PODX, a local Party A ↔ Party B matching platform.\n"
            "Read the user's message in any Indian language, English, mixed language, slang, or transliteration.\n"
            "Understand the meaning. Do NOT force the message into a fixed profession/product/category list.\n"
            "Return exactly one JSON object and no markdown.\n\n"
            "Schema:\n"
            "{\n"
            '  "side": "NEED|OFFER",\n'
            '  "domain": "WORK|WORKERS|SERVICE|PRODUCT|OTHER",\n'
            '  "subject": "short normalized free-form subject",\n'
            '  "quantity": number|null,\n'
            '  "unit": string|null,\n'
            '  "price": number|null,\n'
            '  "currency": string|null,\n'
            '  "when_text": string|null,\n'
            '  "location_text": string|null,\n'
            '  "location_required": true|false,\n'
            '  "constraints": [string, ...],\n'
            '  "confidence": number between 0 and 1\n'
            "}\n\n"
            "Meaning rules:\n"
            "- NEED means the user wants/needs/buys/searches/hires/requests something.\n"
            "- OFFER means the user provides/does/sells/has/offers something.\n"
            "- WORK means the person wants work/a job/task for themselves.\n"
            "- WORKERS means people/manpower/staff are needed or offered for a task.\n"
            "- SERVICE means a service is needed or provided.\n"
            "- PRODUCT means a physical product/material/item is needed or offered.\n"
            "- OTHER is only when none of the above is suitable.\n"
            "- Keep subject free-form and meaningful; do not reject unknown occupations, products, or services.\n"
            "- Extract quantity, budget/price, time, and place only if stated.\n"
            "- Set location_required true when local matching needs GPS/location and no sufficiently specific place was stated.\n"
            "- If a rupee amount is clearly stated, currency should be INR.\n"
            "- Do not invent missing facts.\n\n"
            f"User message: {source_text}"
        )

    @classmethod
    def _parse_json_object(cls, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("AI output did not contain a JSON object")
            payload = json.loads(text[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("AI output must be one JSON object")
        return payload

    @classmethod
    def _normalize_payload(cls, payload: dict[str, Any], source_text: str) -> UniversalRequest:
        side = str(payload.get("side") or "").strip().upper()
        domain = str(payload.get("domain") or "").strip().upper()
        subject = " ".join(str(payload.get("subject") or "").strip().split())

        if side not in VALID_SIDES:
            raise ValueError(f"Unsupported side: {side or '<empty>'}")
        if domain not in VALID_DOMAINS:
            raise ValueError(f"Unsupported domain: {domain or '<empty>'}")
        if not subject:
            raise ValueError("subject is required")

        quantity = cls._optional_number(payload.get("quantity"))
        price = cls._optional_number(payload.get("price"))
        confidence = cls._bounded_confidence(payload.get("confidence"))
        constraints_raw = payload.get("constraints")
        if isinstance(constraints_raw, list):
            constraints = [
                " ".join(str(item).strip().split())
                for item in constraints_raw
                if str(item).strip()
            ]
        elif constraints_raw:
            constraints = [" ".join(str(constraints_raw).strip().split())]
        else:
            constraints = []

        location_text = cls._optional_text(payload.get("location_text"))
        location_required_raw = payload.get("location_required")
        if isinstance(location_required_raw, bool):
            location_required = location_required_raw
        else:
            location_required = location_text is None

        currency = cls._optional_text(payload.get("currency"))
        if currency:
            currency = currency.upper()

        return UniversalRequest(
            side=side,
            domain=domain,
            subject=subject,
            quantity=quantity,
            unit=cls._optional_text(payload.get("unit")),
            price=price,
            currency=currency,
            when_text=cls._optional_text(payload.get("when_text")),
            location_text=location_text,
            location_required=location_required,
            constraints=constraints,
            confidence=confidence,
            source_text=source_text,
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).strip().split())
        return text or None

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned or cleaned in {"-", ".", "-."}:
            return None
        return float(cleaned)

    @staticmethod
    def _bounded_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return max(0.0, min(confidence, 1.0))
