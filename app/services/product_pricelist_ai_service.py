"""AI extraction for seller/business price-list photos and PDFs with confirmation before catalog update."""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


class ProductPriceListAIService:
    MODELS = ("gemini-3.6-flash", "gemini-3.5-flash")

    def __init__(self, api_key: str, catalog_repository, pending_repository, user_repository=None,
                 client: Any | None = None, reengagement_service=None) -> None:
        self.catalog = catalog_repository
        self.pending = pending_repository
        self.users = user_repository
        self.client = client or (genai.Client(api_key=api_key) if api_key else None)
        self.reengagement = reengagement_service

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").casefold().strip().split())
        if clean in {"plist confirm", "price list confirm", "confirm price list", "pricelist confirm"}:
            return self.confirm(sender_mobile)
        if clean in {"plist cancel", "price list cancel", "cancel price list", "pricelist cancel"}:
            return self.cancel(sender_mobile)
        return None

    def process_media(self, sender_mobile: str, content: bytes, mime_type: str, media_ref: str,
                      caption: str | None = None, filename: str | None = None) -> Optional[str]:
        if not content or self.client is None:
            return None
        if not self._is_seller(sender_mobile) and not self._caption_requests_pricelist(caption, filename):
            return None
        payload = self._analyze(content, mime_type, caption, filename)
        if not payload or not bool(payload.get("price_list_detected")):
            return None
        items = self._clean_items(payload.get("items"))
        if not items:
            return None
        source_type = "pdf" if "pdf" in str(mime_type or "").casefold() else "image"
        self.pending.save(sender_mobile, items, media_ref=media_ref, source_type=source_type)
        preview = ", ".join(self._preview(item) for item in items[:10])
        more = f" +{len(items)-10} more" if len(items) > 10 else ""
        return (
            f"🧾 Price listలో {len(items)} product(s) గుర్తించాను: {preview}{more}.\n"
            "Catalog update చేయాలంటే PLIST CONFIRM పంపండి. Save చేయకూడదంటే PLIST CANCEL పంపండి."
        )

    def confirm(self, seller_user_id: str) -> str:
        pending = self.pending.get(seller_user_id)
        if not pending or not pending.get("items"):
            return "Confirm చేయడానికి pending Product Price List లేదు."
        product_ids: List[int] = []
        for item in pending["items"]:
            product_id = self.catalog.upsert_product(
                seller_user_id=seller_user_id,
                subject=item["subject"],
                brand=item.get("brand"),
                variant=item.get("variant"),
                quantity=item.get("quantity"),
                unit=item.get("unit"),
                price=item.get("price"),
                currency=item.get("currency") or "INR",
                stock_status=item.get("stock_status") or "IN_STOCK",
                delivery_available=bool(item.get("delivery_available")),
                pickup_available=True,
            )
            product_ids.append(int(product_id))
        self.pending.clear(seller_user_id)
        self._start_reengagement(str(seller_user_id), product_ids)
        return f"✅ {len(product_ids)} product(s) మీ Product Catalogలో add/update అయ్యాయి."

    def _start_reengagement(self, seller_user_id: str, product_ids: List[int]) -> None:
        if self.reengagement is None or not product_ids:
            return

        def run() -> None:
            for product_id in product_ids:
                try:
                    self.reengagement.notify_product_available(seller_user_id, product_id)
                except Exception as error:
                    print(
                        f"PODX SMART REENGAGEMENT: seller={seller_user_id} product={product_id} "
                        f"failed={type(error).__name__}: {error}",
                        flush=True,
                    )

        threading.Thread(target=run, name="podx-reengagement", daemon=True).start()

    def cancel(self, seller_user_id: str) -> str:
        pending = self.pending.get(seller_user_id)
        if not pending:
            return "Pending Product Price List లేదు."
        self.pending.clear(seller_user_id)
        return "సరే. AI గుర్తించిన price-list products catalogలో save చేయలేదు."

    def _is_seller(self, user_id: str) -> bool:
        if self.users is None:
            return False
        try:
            user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
            role = str(user.get("role") or "").upper()
            caps = {str(x).upper() for x in (self.users.list_capabilities(str(user_id)) or [])}
            return role in {"SELLER", "BUSINESS", "BOTH"} or bool(caps & {"SELLER", "BUSINESS"})
        except Exception:
            return False

    @staticmethod
    def _caption_requests_pricelist(caption: str | None, filename: str | None = None) -> bool:
        text = f"{caption or ''} {filename or ''}".casefold()
        return any(word in text for word in (
            "plist", "price list", "pricelist", "rate list", "rates", "catalog", "catalogue",
            "ప్రైస్ లిస్ట్", "రేట్ లిస్ట్", "ధరల జాబితా", "ధరలు",
        ))

    def _analyze(self, content: bytes, mime_type: str, caption: str | None, filename: str | None) -> Optional[Dict[str, Any]]:
        prompt = self._prompt(caption, filename)
        best = None
        best_confidence = -1.0
        for model in self.MODELS:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=[types.Part.from_bytes(data=content, mime_type=mime_type), prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                payload = self._parse_json(str(getattr(response, "text", "") or ""))
                confidence = self._confidence(payload)
                if confidence > best_confidence:
                    best, best_confidence = payload, confidence
                if bool(payload.get("price_list_detected")) and payload.get("items") and confidence >= 0.65:
                    return payload
            except Exception as error:
                print(f"PODX PRODUCT PRICE LIST AI: model={model} failed={type(error).__name__}: {error}", flush=True)
        if best and bool(best.get("price_list_detected")) and best.get("items") and best_confidence >= 0.45:
            return best
        return None

    @classmethod
    def _clean_items(cls, raw: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()
        if not isinstance(raw, list):
            return result
        for entry in raw:
            data = dict(entry) if isinstance(entry, dict) else ({"name": entry} if isinstance(entry, str) else {})
            subject = " ".join(str(data.get("subject") or data.get("product_name") or data.get("name") or "").strip().split())
            if not subject:
                continue
            brand = cls._text(data.get("brand")); variant = cls._text(data.get("variant"))
            key = (subject.casefold(), (brand or "").casefold(), (variant or "").casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "subject": subject,
                "brand": brand,
                "variant": variant,
                "quantity": cls._number(data.get("quantity")),
                "unit": cls._text(data.get("unit")),
                "price": cls._number(data.get("price")),
                "currency": cls._text(data.get("currency")) or "INR",
                "stock_status": str(data.get("stock_status") or "IN_STOCK").upper(),
                "delivery_available": bool(data.get("delivery_available")),
            })
        return result

    @staticmethod
    def _prompt(caption: str | None, filename: str | None) -> str:
        return (
            "You extract a local business/seller product price list for PODX. Inspect the image or PDF and return one JSON object only. "
            "Set price_list_detected=true only when the media clearly contains products/items with prices, rates, pack sizes, variants, or stock details. "
            "Do not invent unreadable text. A restaurant/catering menu should not be classified as a general product price list. "
            "Extract each visible product. Schema: {\"price_list_detected\":true|false,\"items\":[{\"name\":string,\"brand\":string|null,"
            "\"variant\":string|null,\"quantity\":number|null,\"unit\":string|null,\"price\":number|null,\"currency\":\"INR\","
            "\"stock_status\":\"IN_STOCK|OUT_OF_STOCK|UNKNOWN\",\"delivery_available\":true|false}],\"confidence\":0..1}. "
            f"Caption: {str(caption or '<none>')}. Filename: {str(filename or '<none>')}."
        )

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("no json")
            data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("invalid json")
        return data

    @staticmethod
    def _confidence(payload: Dict[str, Any]) -> float:
        try:
            return max(0.0, min(float(payload.get("confidence") or 0), 1.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or value == "" or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    @staticmethod
    def _text(value: Any) -> str | None:
        text = " ".join(str(value or "").strip().split())
        return text or None

    @staticmethod
    def _preview(item: dict[str, Any]) -> str:
        price = item.get("price")
        return f"{item.get('subject')} ₹{price:g}" if isinstance(price, (int, float)) else str(item.get("subject"))
