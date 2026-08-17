"""AI-driven product schema intelligence for universal PODX commerce flows.

The service is intentionally product-agnostic. It asks AI for valid commercial
units and useful attributes for a free-form product subject, then normalizes
that response into a stable schema used by buyer/seller deal flows.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Any, Callable, Optional

try:
    from google import genai
except Exception:  # pragma: no cover - safe import fallback
    genai = None


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
    """Generate product semantics without hard-coding product names.

    A callable classifier is convenient for tests/custom providers. In normal
    runtime, GEMINI_API_KEY can be supplied and this service asks Gemini for the
    schema and for structured details from a seller reply.
    """

    GENERIC_UNITS = ["piece", "pack", "box"]
    GENERIC_ATTRIBUTES = ["brand", "model_or_variant", "condition_or_quality"]
    GENERIC_BUYER_QUESTIONS = ["price", "availability", "delivery_or_pickup"]
    GENERIC_SELLER_FIELDS = ["price", "availability", "delivery_or_pickup"]

    def __init__(
        self,
        schema_classifier: Optional[Callable[[str], Any]] = None,
        api_key: str = "",
        model: str = "gemini-3.6-flash",
        client: Any | None = None,
    ) -> None:
        self.schema_classifier = schema_classifier
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip() or "gemini-3.6-flash"
        self._client = client
        if self._client is None and self.api_key and genai is not None:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

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

        if self._client is not None:
            try:
                raw = self._ai_json(self._schema_prompt(clean_subject))
                normalized = self._normalize(clean_subject, raw)
                if normalized is not None:
                    return normalized.to_dict()
            except Exception:
                pass

        return self._fallback(clean_subject).to_dict()

    def extract_details(self, subject: str, text: str) -> dict[str, Any]:
        """Extract schema-aware deal details from a free-form seller reply.

        Returns only facts explicitly stated. Unknown product-specific facts are
        stored under ``attributes`` so no product-name-specific parser is needed.
        """
        clean_subject = " ".join(str(subject or "").strip().split())
        clean_text = " ".join(str(text or "").strip().split())
        if not clean_subject or not clean_text or self._client is None:
            return {}
        schema = self.schema_for(clean_subject)
        try:
            raw = self._ai_json(self._details_prompt(clean_subject, clean_text, schema))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}

        result: dict[str, Any] = {}
        for key in ("quantity", "rate"):
            value = self._optional_number(raw.get(key))
            if value is not None:
                result[key] = value
        for key in ("unit", "rate_unit", "availability", "fulfilment"):
            value = self._clean_text(raw.get(key))
            if value:
                result[key] = value
        attrs = raw.get("attributes")
        if isinstance(attrs, dict):
            cleaned_attrs = {}
            for key, value in attrs.items():
                k = self._clean_text(key)
                v = self._clean_text(value)
                if k and v:
                    cleaned_attrs[k] = v
            if cleaned_attrs:
                result["attributes"] = cleaned_attrs
                # Keep legacy summary compatibility while preserving structure.
                result["quality"] = ", ".join(
                    f"{k}: {v}" for k, v in list(cleaned_attrs.items())[:5]
                )
        return result

    def validate_unit(self, subject: str, unit: str) -> bool:
        value = self._clean_token(unit)
        if not value:
            return False
        schema = self.schema_for(subject)
        # Low-confidence fallback must never reject a legitimate user unit.
        if float(schema.get("confidence") or 0.0) < 0.5:
            return True
        allowed = {self._clean_token(item) for item in schema.get("valid_units") or []}
        return value in allowed

    def relevant_missing_fields(self, subject: str, details: dict[str, Any]) -> list[str]:
        schema = self.schema_for(subject)
        missing: list[str] = []
        if schema.get("quantity_required") and details.get("quantity") in (None, ""):
            missing.append("quantity")
        if schema.get("price_required") and details.get("rate") in (None, "") and details.get("price") in (None, ""):
            missing.append("price")
        attributes = details.get("attributes") if isinstance(details.get("attributes"), dict) else {}
        for field in schema.get("seller_fields") or []:
            key = self._clean_token(field).replace(" ", "_")
            if key in {"price", "rate", "quantity"}:
                continue
            if key in {"delivery_or_pickup", "fulfilment", "fulfillment"}:
                present = details.get("fulfilment") not in (None, "")
            elif key in {"availability", "available"}:
                present = details.get("availability") not in (None, "")
            else:
                present = details.get(key) not in (None, "") or attributes.get(field) not in (None, "") or attributes.get(key) not in (None, "")
            if not present:
                missing.append(field)
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

    def _ai_json(self, prompt: str) -> dict[str, Any]:
        interaction = self._client.interactions.create(model=self.model, input=prompt, store=False)
        raw = str(getattr(interaction, "output_text", "") or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("AI schema output did not contain JSON")
            payload = json.loads(raw[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("AI schema output must be an object")
        return payload

    @staticmethod
    def _schema_prompt(subject: str) -> str:
        return (
            "You are PODX Product Schema Brain. Understand the physical product semantically, without relying on a fixed category list. "
            "Return exactly one JSON object. Choose only commercially sensible units and fields. Never suggest nonsensical units "
            "(for example litres for solid construction material, kilograms for a television). Do not invent regulatory claims.\n"
            "Schema: {\"valid_units\":[string],\"key_attributes\":[string],\"optional_attributes\":[string],"
            "\"buyer_questions\":[string],\"seller_fields\":[string],\"quantity_required\":bool,\"price_required\":bool,\"confidence\":0..1}.\n"
            "seller_fields should contain only details genuinely useful to finish a local buyer-seller deal; use delivery_or_pickup for fulfilment.\n"
            f"Product subject: {subject}"
        )

    @staticmethod
    def _details_prompt(subject: str, text: str, schema: dict[str, Any]) -> str:
        return (
            "You are PODX Deal Detail Extractor. Extract only facts explicitly stated by the seller. Return exactly JSON and no markdown. "
            "Do not infer missing values. Use a valid product unit when the text states one. Put product-specific facts under attributes.\n"
            "Schema: {\"quantity\":number|null,\"unit\":string|null,\"rate\":number|null,\"rate_unit\":string|null,"
            "\"availability\":string|null,\"fulfilment\":\"delivery|pickup\"|null,\"attributes\":{string:string}}\n"
            f"Product: {subject}\nProduct schema: {json.dumps(schema, ensure_ascii=False)}\nSeller message: {text}"
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
    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).strip().split())
        return text or None

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if value is None or value == "" or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            cleaned = re.sub(r"[^0-9.\-]", "", str(value))
            try:
                return float(cleaned) if cleaned else None
            except ValueError:
                return None

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(number, 1.0))
