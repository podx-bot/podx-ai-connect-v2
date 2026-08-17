"""AI-driven product schema intelligence for universal PODX commerce flows.

The service is intentionally product-agnostic. It asks an AI classifier for
valid commercial units and useful attributes for a free-form product subject,
then normalizes the response into a stable schema used by buyer/seller flows.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Optional


@dataclass
class ProductSchema:
    subject: str
    valid_units: list[str]
    key_attributes: list[str]
    optional_attributes: list[str]
    buyer_questions: list[str]
    seller_fields: list[str]
    quantity_required: bool = True
    price_required: bool = True
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UniversalProductSchemaService:
    """Generate a product-specific schema without hard-coding product names."""

    GENERIC_UNITS = ["piece", "pack", "box"]
    GENERIC_ATTRIBUTES = ["brand", "model_or_variant", "condition_or_quality"]
    GENERIC_BUYER_QUESTIONS = ["price", "availability", "delivery_or_pickup"]
    GENERIC_SELLER_FIELDS = ["price", "availability", "delivery_or_pickup"]

    def __init__(
        self,
        schema_classifier: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.schema_classifier = schema_classifier

    def schema_for(self, subject: str) -> dict[str, Any]:
        clean_subject = " ".join(str(subject or "").strip().split())
        if not clean_subject:
            return self._fallback("item").to_dict()

        if callable(self.schema_classifier):
            try:
                raw = self.schema_classifier(clean_subject)
                normalized = self._normalize(clean_subject, raw)
                if normalized is not None:
                    return normalized.to_dict()
            except Exception:
                pass

        return self._fallback(clean_subject).to_dict()

    def validate_unit(self, subject: str, unit: str) -> bool:
        value = self._clean_token(unit)
        if not value:
            return False
        schema = self.schema_for(subject)
        allowed = {self._clean_token(item) for item in schema.get("valid_units") or []}
        return value in allowed

    def relevant_missing_fields(self, subject: str, details: dict[str, Any]) -> list[str]:
        schema = self.schema_for(subject)
        missing: list[str] = []
        if schema.get("quantity_required") and details.get("quantity") in (None, ""):
            missing.append("quantity")
        if schema.get("price_required") and details.get("rate") in (None, "") and details.get("price") in (None, ""):
            missing.append("price")
        for field in schema.get("seller_fields") or []:
            key = str(field).strip()
            if key in {"price", "quantity"}:
                continue
            if key and details.get(key) in (None, ""):
                missing.append(key)
        return list(dict.fromkeys(missing))

    @classmethod
    def _normalize(cls, subject: str, raw: Any) -> ProductSchema | None:
        if not isinstance(raw, dict):
            return None

        units = cls._string_list(raw.get("valid_units"))
        key_attributes = cls._string_list(raw.get("key_attributes"))
        optional_attributes = cls._string_list(raw.get("optional_attributes"))
        buyer_questions = cls._string_list(raw.get("buyer_questions"))
        seller_fields = cls._string_list(raw.get("seller_fields"))
        if not units:
            return None

        return ProductSchema(
            subject=subject,
            valid_units=units,
            key_attributes=key_attributes,
            optional_attributes=optional_attributes,
            buyer_questions=buyer_questions or list(cls.GENERIC_BUYER_QUESTIONS),
            seller_fields=seller_fields or list(cls.GENERIC_SELLER_FIELDS),
            quantity_required=bool(raw.get("quantity_required", True)),
            price_required=bool(raw.get("price_required", True)),
            confidence=cls._confidence(raw.get("confidence")),
        )

    @classmethod
    def _fallback(cls, subject: str) -> ProductSchema:
        return ProductSchema(
            subject=subject,
            valid_units=list(cls.GENERIC_UNITS),
            key_attributes=list(cls.GENERIC_ATTRIBUTES),
            optional_attributes=[],
            buyer_questions=list(cls.GENERIC_BUYER_QUESTIONS),
            seller_fields=list(cls.GENERIC_SELLER_FIELDS),
            quantity_required=True,
            price_required=True,
            confidence=0.2,
        )

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        cleaned = []
        for item in value:
            text = " ".join(str(item or "").strip().split())
            if text:
                cleaned.append(text)
        return list(dict.fromkeys(cleaned))

    @staticmethod
    def _clean_token(value: Any) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(number, 1.0))
