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
    RESERVED_FIELD_PREFIXES = (
        "test", "testing", "debug", "internal", "temp", "temporary", "mock",
        "sample", "placeholder", "dummy", "example", "dev", "qa",
    )
    SEMANTIC_FIELD_GROUPS = {
        "model": {
            "model", "model_number", "exact_model", "exact_model_number",
            "model_no", "model_code", "product_model", "model_or_variant",
        },
        "condition": {
            "condition", "condition_details", "item_condition", "product_condition",
            "condition_or_quality", "quality_condition", "state_condition",
        },
        "working_status": {
            "working_status", "functionality_status", "functional_status",
            "function_status", "working_condition", "operational_status",
            "working", "functionality",
        },
        "accessories": {
            "accessories", "included_accessories", "included_items", "box_contents",
            "in_the_box", "included_parts", "included_components",
        },
        "brand": {"brand", "brand_name", "make", "manufacturer_brand"},
        "screen_size": {"screen_size", "display_size", "screen_dimension"},
        "availability": {"availability", "available", "stock_status", "availability_status"},
        "fulfilment": {
            "fulfilment", "fulfillment", "delivery_or_pickup", "delivery_pickup",
            "delivery_mode", "fulfilment_mode", "fulfillment_mode",
        },
        "warranty": {"warranty", "warranty_details", "warranty_status", "warranty_period"},
    }

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
                if k and v and self._is_safe_field_name(k):
                    cleaned_attrs[k] = v
            if cleaned_attrs:
                result["attributes"] = cleaned_attrs
                result["quality"] = ", ".join(
                    f"{k}: {v}" for k, v in list(cleaned_attrs.items())[:5]
                )
        return result

    def validate_unit(self, subject: str, unit: str) -> bool:
        value = self._clean_token(unit)
        if not value:
            return False
        schema = self.schema_for(subject)
        if float(schema.get("confidence") or 0.0) < 0.5:
            return True
        allowed = {self._clean_token(item) for item in schema.get("valid_units") or []}
        return value in allowed

    def relevant_missing_fields(self, subject: str, details: dict[str, Any]) -> list[str]:
        schema = self.schema_for(subject)
        missing: list[str] = []
        has_quantity = details.get("quantity") not in (None, "")
        has_price = details.get("rate") not in (None, "") or details.get("price") not in (None, "")
        has_rate_unit = details.get("rate_unit") not in (None, "")

        if schema.get("quantity_required") and not has_quantity and (not has_price or has_rate_unit):
            missing.append("quantity")
        if schema.get("price_required") and not has_price:
            missing.append("price")

        attributes = details.get("attributes") if isinstance(details.get("attributes"), dict) else {}
        present_canonical: set[str] = set()
        for key, value in details.items():
            if key == "attributes" or value in (None, ""):
                continue
            present_canonical.add(self._canonical_field_name(key))
        for key, value in attributes.items():
            if value not in (None, ""):
                present_canonical.add(self._canonical_field_name(key))

        for field in schema.get("seller_fields") or []:
            if not self._is_safe_field_name(field):
                continue
            canonical = self._canonical_field_name(field)
            if canonical in {"price", "rate", "quantity"}:
                continue
            if canonical in present_canonical:
                continue
            missing.append(field)
        return list(dict.fromkeys(missing))

    @classmethod
    def _normalize(cls, subject: str, raw: Any) -> ProductSchema | None:
        if not isinstance(raw, dict):
            return None
        units = cls._string_list(raw.get("valid_units"))
        key_attributes = cls._safe_field_list(raw.get("key_attributes"))
        optional_attributes = cls._safe_field_list(raw.get("optional_attributes"))
        buyer_questions = cls._safe_field_list(raw.get("buyer_questions"))
        seller_fields = cls._safe_field_list(raw.get("seller_fields"))
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
            "Return exactly one JSON object. Choose only commercially sensible TRANSACTION units and fields. valid_units means units used to buy/sell quantity "
            "(piece, bag, kg, litre, pack, metre, etc.), never specification units such as screen inches, Hz, watts, storage GB or dimensions. "
            "Never suggest nonsensical units (for example litres for solid construction material, kilograms for a television). Do not invent regulatory claims. "
            "Never output test/debug/internal/temp/mock/sample/placeholder fields. Prefer stable common field names such as model, condition, working_status, included_accessories, brand, screen_size, warranty, availability and delivery_or_pickup instead of inventing synonyms. "
            "For normally singular durable items sold at one quoted total price, quantity_required should be false.\n"
            "Schema: {\"valid_units\":[string],\"key_attributes\":[string],\"optional_attributes\":[string],"
            "\"buyer_questions\":[string],\"seller_fields\":[string],\"quantity_required\":bool,\"price_required\":bool,\"confidence\":0..1}.\n"
            "seller_fields should contain only details genuinely useful to finish a local buyer-seller deal; use delivery_or_pickup for fulfilment.\n"
            f"Product subject: {subject}"
        )

    @staticmethod
    def _details_prompt(subject: str, text: str, schema: dict[str, Any]) -> str:
        return (
            "You are PODX Deal Detail Extractor. Extract only facts explicitly stated by the seller. Return exactly JSON and no markdown. "
            "Do not infer missing values. A standalone quoted price is the total/lump-sum item price unless the seller explicitly says per/unit. "
            "Use a valid transaction unit only when the text states one. Put product-specific facts under attributes. Never create test/debug/internal/placeholder attributes. "
            "Prefer stable common attribute names such as model, condition, working_status, included_accessories, brand, screen_size and warranty rather than new synonyms.\n"
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

    @classmethod
    def _safe_field_list(cls, value: Any) -> list[str]:
        return [item for item in cls._string_list(value) if cls._is_safe_field_name(item)]

    @classmethod
    def _is_safe_field_name(cls, value: Any) -> bool:
        token = cls._clean_token(value).replace("-", "_").replace(" ", "_")
        if not token or len(token) > 64:
            return False
        if not re.fullmatch(r"[a-z0-9_]+", token):
            return False
        parts = [part for part in token.split("_") if part]
        if not parts:
            return False
        return not any(
            part.startswith(prefix)
            for part in parts
            for prefix in cls.RESERVED_FIELD_PREFIXES
        )

    @classmethod
    def _canonical_field_name(cls, value: Any) -> str:
        token = cls._clean_token(value).replace("-", "_").replace(" ", "_")
        token = re.sub(r"_+", "_", token).strip("_")
        for canonical, aliases in cls.SEMANTIC_FIELD_GROUPS.items():
            if token == canonical or token in aliases:
                return canonical
        return token

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
