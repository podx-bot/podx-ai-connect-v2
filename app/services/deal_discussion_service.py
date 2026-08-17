"""Private deal clarification between matched parties before order/contact actions."""
from __future__ import annotations

import os
import re
from typing import Any


class DealDiscussionService:
    def __init__(self, repository, whatsapp_service, contact_resolver, product_schema_service=None) -> None:
        self.repository = repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.product_schema = product_schema_service or self._auto_product_schema_service()

    @staticmethod
    def _auto_product_schema_service():
        try:
            from app.services.universal_product_schema_service import UniversalProductSchemaService
            return UniversalProductSchemaService(
                api_key=os.getenv("GEMINI_API_KEY", "").strip(),
                model=os.getenv("GEMINI_VOICE_MODEL", "gemini-3.6-flash").strip() or "gemini-3.6-flash",
            )
        except Exception:
            return None

    def _send_buttons_or_text(self, mobile, body, buttons):
        sender = getattr(self.whatsapp, "send_reply_buttons", None)
        if callable(sender):
            return sender(mobile, body, buttons)
        return self.whatsapp.send_text_message(mobile, body)

    def start(self, request, buyer: str, seller: str):
        request_id = int(request["id"])
        seed = {}
        for key in ("quantity", "unit", "price", "currency", "when_text", "location_text"):
            if request.get(key) not in (None, ""):
                seed[key] = request.get(key)
        self.repository.start(request_id, buyer, seller, seed)
        buyer_mobile = self._mobile(buyer)
        seller_mobile = self._mobile(seller)
        self.whatsapp.send_text_message(
            buyer_mobile,
            "✅ Seller available అని confirm చేశారు. ఇప్పుడు PODX deal details sellerతో clarify చేస్తోంది. Contact details ఇప్పుడే share కావు.",
        )
        prompt = self._seller_prompt(request, seed)
        seller_delivery = self.whatsapp.send_text_message(seller_mobile, prompt)
        return {"status": "WAITING_SELLER_DETAILS", "request_id": request_id, "notification": seller_delivery}

    def consume_seller_text(self, request, buyer: str, seller: str, text: str):
        request_id = int(request["id"])
        deal = self.repository.get(request_id, seller)
        if not deal or deal.get("status") not in {"WAITING_SELLER_DETAILS", "WAITING_SELLER_REVISION"}:
            return None
        parsed = self._parse_details(request, text)
        if self._category(request) == "PRODUCT" and self.product_schema is not None:
            try:
                ai_details = self.product_schema.extract_details(str(request.get("subject") or "item"), text)
                if isinstance(ai_details, dict):
                    parsed = self._merge_detail_dicts(parsed, ai_details)
            except Exception:
                pass
        merged = self._merge_detail_dicts(deal.get("details") or {}, parsed)

        invalid_unit = self._invalid_product_unit(request, merged)
        if invalid_unit:
            return invalid_unit

        missing = self._missing_required(request, merged, text)
        if missing:
            labels = ", ".join(missing)
            return f"Deal complete చేయడానికి ఇంకా {labels} చెప్పండి. ఇప్పటికే చెప్పిన details మళ్లీ అవసరం లేదు."
        updated = self.repository.save_seller_details(
            request_id,
            seller,
            parsed,
            text,
            revised=deal.get("status") == "WAITING_SELLER_REVISION",
        )
        buyer_mobile = self._mobile(buyer)
        summary = self._summary(request, updated)
        self._send_buttons_or_text(
            buyer_mobile,
            summary + "\n\nఈ deal సరేనా? మార్పు కావాలంటే PODX ద్వారా అడగండి.",
            [
                {"id": f"DEAL_CONFIRM {request_id} {seller}", "title": "✅ Deal OK"},
                {"id": f"DEAL_CHANGE {request_id} {seller}", "title": "💬 మార్పు అడగండి"},
            ],
        )
        return "✅ Deal details save చేశాను. Buyerకి summary పంపాను; contact ఇంకా privateగానే ఉంది."

    @staticmethod
    def _merge_detail_dicts(base, incoming):
        merged = dict(base or {})
        for key, value in dict(incoming or {}).items():
            if key == "attributes" and isinstance(value, dict):
                attrs = dict(merged.get("attributes") or {})
                attrs.update(value)
                merged["attributes"] = attrs
            elif value not in (None, ""):
                merged[key] = value
        return merged

    def ask_for_change(self, request, buyer: str, seller: str):
        deal = self.repository.get(int(request["id"]), seller)
        if not deal or deal.get("status") not in {
            "WAITING_BUYER_CONFIRM",
            "WAITING_SELLER_DETAILS",
            "WAITING_SELLER_REVISION",
        }:
            return "ఈ deal ఇప్పుడు change requestకి readyగా లేదు."
        self.repository.mark_waiting_buyer_change(int(request["id"]), seller)
        return "💬 ఏ detail మార్చాలి? ఉదా: rate తగ్గించండి / variant మార్చండి / delivery కావాలి. మీ మాటల్లో పంపండి."

    def consume_buyer_change(self, request, buyer: str, seller: str, text: str):
        request_id = int(request["id"])
        deal = self.repository.get(request_id, seller)
        if not deal or deal.get("status") != "WAITING_BUYER_CHANGE":
            return None
        parsed = self._parse_details(request, text)
        parsed.pop("seller_note", None)
        parsed.pop("rate", None)
        parsed.pop("rate_unit", None)
        updated = self.repository.save_buyer_change(request_id, seller, text, details=parsed)
        seller_mobile = self._mobile(seller)
        self.whatsapp.send_text_message(
            seller_mobile,
            f"💬 Buyer deal clarification:\n{updated.get('buyer_question') or text}\n\nAgree/updated rate-quality-delivery details మీ మాటల్లో reply చేయండి. PODX buyerకి మాత్రమే relay చేస్తుంది.",
        )
        return "✅ మీ clarification sellerకి పంపాను. Seller reply వచ్చిన తర్వాత updated deal summary ఇస్తాను."

    def confirm(self, request, buyer: str, seller: str):
        request_id = int(request["id"])
        deal = self.repository.get(request_id, seller)
        if not deal or str(deal.get("buyer_user_id")) != str(buyer):
            return {"status": "DEAL_NOT_FOUND"}
        if deal.get("status") != "WAITING_BUYER_CONFIRM":
            return {"status": "DEAL_NOT_READY"}
        deal = self.repository.confirm(request_id, seller)
        buyer_mobile = self._mobile(buyer)
        seller_mobile = self._mobile(seller)
        self.whatsapp.send_text_message(seller_mobile, "✅ Buyer deal summaryని accept చేశారు. Contact ఇంకా share కాలేదు.")
        result = self._send_buttons_or_text(
            buyer_mobile,
            self._summary(request, deal) + "\n\n✅ Deal confirmed. ఇప్పుడు next step ఎంచుకోండి.",
            [
                {"id": f"ORDER_CONTINUE {request_id} {seller}", "title": "📦 Order Continue"},
                {"id": f"DIRECT_TALK {request_id} {seller}", "title": "📞 Direct Talk"},
            ],
        )
        return {"status": "DEAL_CONFIRMED", "notification": result}

    def is_confirmed(self, request_id: int, seller: str) -> bool:
        deal = self.repository.get(request_id, seller)
        return bool(deal and deal.get("status") == "CONFIRMED")

    def pending_for_seller(self, seller: str):
        return self.repository.latest_for_seller(seller, ("WAITING_SELLER_DETAILS", "WAITING_SELLER_REVISION"))

    def pending_for_buyer_change(self, buyer: str):
        return self.repository.latest_for_buyer(buyer, ("WAITING_BUYER_CHANGE",))

    def pending_for_buyer_summary(self, buyer: str):
        return self.repository.latest_for_buyer(
            buyer,
            ("WAITING_BUYER_CONFIRM", "WAITING_SELLER_DETAILS", "WAITING_SELLER_REVISION"),
        )

    def _mobile(self, user_id: str) -> str:
        contact = self.contact_resolver(str(user_id)) or {}
        return str(contact.get("mobile") or contact.get("phone") or user_id)

    @staticmethod
    def _category(request) -> str:
        return str(request.get("domain") or "OTHER").upper()

    @staticmethod
    def _normalize_unit(unit: Any) -> str:
        value = str(unit or "").strip().casefold()
        if value in {"kg", "kgs", "kilogram", "kilograms", "కేజీ", "కేజీలు", "కిలో", "కిలోలు"}:
            return "kg"
        if value in {"g", "gm", "gms", "gram", "grams"}:
            return "g"
        if value in {"l", "ltr", "litre", "litres", "liter", "liters"}:
            return "l"
        if value in {"ml", "millilitre", "millilitres", "milliliter", "milliliters"}:
            return "ml"
        if value in {"piece", "pieces", "pc", "pcs", "unit", "units"}:
            return "piece"
        if value in {"bag", "bags", "pack", "packs", "packet", "packets", "box", "boxes"}:
            return value.rstrip("s")
        if value in {"hour", "hours", "hr", "hrs"}:
            return "hour"
        if value in {"day", "days"}:
            return "day"
        return value

    def _schema(self, request):
        if self._category(request) != "PRODUCT" or self.product_schema is None:
            return None
        try:
            return self.product_schema.schema_for(str(request.get("subject") or "item"))
        except Exception:
            return None

    def _seller_prompt(self, request, seed) -> str:
        subject = str(request.get("subject") or "item")
        existing = []
        if seed.get("quantity") is not None:
            existing.append(f"Qty {seed['quantity']} {seed.get('unit') or ''}".strip())
        if seed.get("price") is not None:
            existing.append(f"existing price/budget ₹{seed['price']}")
        known = f" ఇప్పటికే: {', '.join(existing)}." if existing else ""
        category = self._category(request)
        if category == "PRODUCT":
            schema = self._schema(request)
            if schema and float(schema.get("confidence") or 0.0) >= 0.5:
                fields = list(dict.fromkeys((schema.get("seller_fields") or []) + (schema.get("key_attributes") or [])))
                fields_text = ", ".join(str(x) for x in fields[:8]) or "price, availability, delivery/pickup"
                units = ", ".join(str(x) for x in (schema.get("valid_units") or [])[:6])
                unit_text = f" ఈ productకి సరైన units: {units}." if units else ""
                return f"🤝 PODX Deal Discussion\n{subject}.{known}\nBuyerతో contact share చేసే ముందు relevant details మాత్రమే చెప్పండి: {fields_text}.{unit_text} ఇప్పటికే ఉన్న detail మళ్లీ చెప్పాల్సిన అవసరం లేదు. ఒకే text/voice replyలో చెప్పవచ్చు."
            fields = "price/rate, relevant type/variant/size (ఉంటే), availability, delivery/pickup"
        elif category in {"SERVICE", "SERVICES"}:
            fields = "work scope, rate, available date/time, location/visit details"
        elif category in {"WORK", "WORKERS", "JOB", "JOBS"}:
            fields = "salary/rate, timing, skill/experience requirement, work location"
        else:
            fields = "price/rate, quantity లేదా scope, availability/time, delivery/fulfilment"
        return f"🤝 PODX Deal Discussion\n{subject}.{known}\nBuyerతో contact share చేసే ముందు {fields} చెప్పండి. ఇప్పటికే ఉన్న detail మళ్లీ చెప్పాల్సిన అవసరం లేదు. ఒకే text/voice replyలో చెప్పవచ్చు."

    @classmethod
    def _parse_details(cls, request, text: str) -> dict[str, Any]:
        clean = " ".join(str(text or "").strip().split())
        low = clean.casefold()
        result: dict[str, Any] = {"seller_note": clean}

        unit_words = r"kg|kgs|kilograms?|కేజీ|కేజీలు|కిలో|కిలోలు|g|gm|gms|grams?|l|ltr|litres?|liters?|ml|pieces?|pc|pcs|units?|bags?|packs?|packets?|boxes?|hours?|hrs?|days?"
        qty = re.search(rf"(\d+(?:\.\d+)?)\s*({unit_words})", low, re.I)
        if qty:
            result["quantity"] = float(qty.group(1))
            result["unit"] = cls._normalize_unit(qty.group(2))

        price = re.search(r"(?:₹|rs\.?|inr|రూ\.?|రూపాయలు?)\s*(\d+(?:\.\d+)?)", low, re.I)
        if not price:
            price = re.search(r"(\d+(?:\.\d+)?)\s*(?:rs\.?|inr|రూ\.?|రూపాయలు?)", low, re.I)
        if not price:
            price = re.search(rf"(\d+(?:\.\d+)?)\s*(?:/|per\s+)({unit_words})", low, re.I)
        if price:
            result["rate"] = float(price.group(1))
            if len(price.groups()) > 1 and price.group(2):
                result["rate_unit"] = cls._normalize_unit(price.group(2))
            else:
                unit_match = re.search(rf"(?:/|per\s+)({unit_words})", low, re.I)
                if unit_match:
                    result["rate_unit"] = cls._normalize_unit(unit_match.group(1))
                elif re.search(r"\b(?:bag|pack|packet|box)\b", low):
                    pack_match = re.search(r"\b(bag|pack|packet|box)\b", low)
                    if pack_match:
                        result["rate_unit"] = cls._normalize_unit(pack_match.group(1))

        labelled = re.search(r"(?:quality|type|variant|brand|model|size)\s*[:=-]?\s*([\w\- ]{2,40})", low, re.I)
        if labelled:
            value = re.split(r"\b(?:delivery|pickup|available|today|tomorrow|rs|inr)\b", labelled.group(1), maxsplit=1)[0].strip(" ,.-")
            if value:
                result["quality"] = value
        else:
            quality_terms = (
                "fresh", "skinless", "with skin", "whole", "cut", "boneless", "organic", "premium",
                "grade", "new", "used", "sealed", "original", "small", "medium", "large", "xl", "xxl",
                "ఫ్రెష్", "బోన్లెస్", "క్వాలిటీ", "మంచి క్వాలిటీ",
            )
            found_quality = [term for term in quality_terms if term in low]
            if found_quality:
                result["quality"] = ", ".join(found_quality[:4])
            else:
                words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", low)
                stop = {
                    "only", "pickup", "delivery", "available", "today", "tomorrow", "price", "rate",
                    "per", "bag", "bags", "pack", "packs", "packet", "packets", "box", "boxes",
                    "kg", "kgs", "gram", "grams", "piece", "pieces", "unit", "units", "need", "want",
                    "have", "sell", "selling", "buy", "buying",
                }
                subject_words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", str(request.get("subject") or "").casefold()))
                candidates = [w for w in words if w not in stop and w not in subject_words and not w.isdigit()]
                if candidates:
                    result["quality"] = " ".join(candidates[-3:])

        if any(term in low for term in ("today", "ఈరోజు", "available", "ready", "ఇప్పుడు", "ఉంది", "stock")):
            result["availability"] = "available/today"
        elif any(term in low for term in ("tomorrow", "రేపు")):
            result["availability"] = "tomorrow"
        if "delivery" in low or "డెలివరీ" in low:
            result["fulfilment"] = "delivery"
        elif "pickup" in low or "pick up" in low or "పికప్" in low:
            result["fulfilment"] = "pickup"
        return result

    def _invalid_product_unit(self, request, details):
        if self._category(request) != "PRODUCT" or self.product_schema is None:
            return None
        subject = str(request.get("subject") or "item")
        schema = self._schema(request)
        if not schema or float(schema.get("confidence") or 0.0) < 0.5:
            return None
        for key in ("unit", "rate_unit"):
            unit = details.get(key)
            if unit and not self.product_schema.validate_unit(subject, unit):
                valid = ", ".join(str(x) for x in (schema.get("valid_units") or [])[:6])
                return f"ఈ {subject}కి '{unit}' unit సరిపోలడం లేదు. సాధారణంగా సరైన units: {valid}. మీ dealలో సరైన unit చెప్పండి."
        return None

    def _missing_required(self, request, details, raw_text: str):
        category = self._category(request)
        missing = []
        if category == "PRODUCT":
            combined = self._merge_detail_dicts(request, details)
            schema = self._schema(request)
            if schema and float(schema.get("confidence") or 0.0) >= 0.5 and self.product_schema is not None:
                return self.product_schema.relevant_missing_fields(str(request.get("subject") or "item"), combined)
            if details.get("quantity") is None and request.get("quantity") is None:
                missing.append("quantity")
            if details.get("rate") is None and request.get("price") is None:
                missing.append("price/rate")
            if not details.get("fulfilment"):
                missing.append("delivery/pickup")
        elif category in {"SERVICE", "SERVICES"}:
            if details.get("rate") is None and request.get("price") is None:
                missing.append("rate")
            if len(str(raw_text or "").strip()) < 8:
                missing.append("scope/time")
        elif category in {"WORK", "WORKERS", "JOB", "JOBS"}:
            if details.get("rate") is None and request.get("price") is None:
                missing.append("salary/rate")
            if len(str(raw_text or "").strip()) < 8:
                missing.append("timing/skill")
        return missing

    def _summary(self, request, deal) -> str:
        details = dict(deal.get("details") or {})
        bits = ["🤝 PODX Deal Summary", f"Item: {request.get('subject') or 'Requirement'}"]
        quantity = details.get("quantity", request.get("quantity"))
        unit = self._normalize_unit(details.get("unit", request.get("unit")))
        if quantity is not None:
            bits.append(f"Quantity: {quantity:g} {unit or ''}".strip() if isinstance(quantity, float) else f"Quantity: {quantity} {unit or ''}".strip())
        rate = details.get("rate")
        rate_unit = self._normalize_unit(details.get("rate_unit") or unit)
        if rate is not None:
            bits.append(f"Rate: ₹{rate:g} / {rate_unit or 'unit'}")
        elif request.get("price") is not None:
            bits.append(f"Price/Budget: ₹{request.get('price')}")
        if quantity is not None and rate is not None and unit and rate_unit and unit == rate_unit:
            try:
                total = float(quantity) * float(rate)
                bits.append(f"Total: ₹{total:,.0f}" if total.is_integer() else f"Total: ₹{total:,.2f}")
            except (TypeError, ValueError):
                pass
        attrs = details.get("attributes") if isinstance(details.get("attributes"), dict) else {}
        if attrs:
            bits.append("Details: " + ", ".join(f"{k}: {v}" for k, v in list(attrs.items())[:6]))
        elif details.get("quality"):
            bits.append(f"Quality/Type: {details['quality']}")
        if details.get("availability"):
            bits.append(f"Availability: {details['availability']}")
        if details.get("fulfilment"):
            bits.append(f"Fulfilment: {details['fulfilment']}")
        note = str(deal.get("seller_note") or details.get("seller_note") or "").strip()
        if note:
            bits.append(f"Seller note: {note}")
        if deal.get("buyer_question"):
            bits.append(f"Buyer clarification: {deal['buyer_question']}")
        bits.append("🔒 Contact details ఇంకా privateగానే ఉన్నాయి.")
        return "\n".join(bits)
