"""WhatsApp runtime for grocery basket RFQs and seller quote replies."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class GroceryRFQRuntimeService:
    BUYER_PREFIXES = ("grocery", "groceries", "kirana", "గ్రోసరీ", "కిరాణా")
    QUOTE_COMMANDS = {"grocery quotes", "kirana quotes", "గ్రోసరీ కోట్స్", "కిరాణా కోట్స్"}

    def __init__(self, repository, ranking_service, whatsapp_service, contact_resolver, user_repository=None) -> None:
        self.repository = repository
        self.ranking = ranking_service
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None
        lowered = clean.casefold()
        handles_message = lowered.startswith("gquote") or lowered in self.QUOTE_COMMANDS or any(lowered.startswith(prefix) for prefix in self.BUYER_PREFIXES)
        if not handles_message:
            return None
        if not self._registered(sender_user_id):
            return None
        seller_reply = self._consume_seller_quote(sender_user_id, clean)
        if seller_reply is not None:
            return seller_reply
        if lowered in self.QUOTE_COMMANDS:
            return self._format_latest_quotes(sender_user_id)
        items = self._parse_items(clean)
        if len(items) < 2:
            return "🛒 Grocery RFQ కోసం కనీసం 2 items పంపండి. Example: Grocery: rice 5kg, oil 1L, sugar 2kg"
        rfq_id = self.repository.create_rfq(sender_user_id, items)
        stored_items = self.repository.list_items(rfq_id)
        sellers = self.repository.find_candidate_sellers(stored_items, exclude_user_id=sender_user_id, limit=12)
        sent = 0
        for seller in sellers:
            seller_user_id = str(seller["seller_user_id"])
            if not self.repository.add_target(rfq_id, seller_user_id):
                continue
            contact = self.contact_resolver(seller_user_id) or {}
            mobile = str(contact.get("mobile") or contact.get("phone") or seller_user_id)
            self.whatsapp.send_text_message(mobile, self._seller_prompt(rfq_id, stored_items))
            sent += 1
        if sent == 0:
            return f"🛒 Grocery RFQ #{rfq_id} save చేశాను. ప్రస్తుతం catalog match ఉన్న seller దొరకలేదు; RFQ OPENగా ఉంది."
        return f"🛒 Grocery RFQ #{rfq_id} save అయింది. {sent} matching seller{'s' if sent != 1 else ''}కి quote request పంపాను. Quotes వచ్చినప్పుడు మీకు పంపిస్తాను."

    def _registered(self, user_id: str) -> bool:
        if self.users is None:
            return True
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return int(user.get("registration_complete") or 0) == 1

    def _consume_seller_quote(self, seller_user_id: str, message: str) -> Optional[str]:
        if not message.casefold().startswith("gquote"):
            return None
        parsed = self._parse_quote_message(message)
        if parsed is None:
            return "Format: GQUOTE <RFQ ID> rice=300, oil=150, sugar=90, delivery=30"
        rfq_id, price_map, delivery_fee = parsed
        target = self.repository.target_for_seller(seller_user_id, rfq_id=rfq_id)
        if target is None:
            return f"RFQ #{rfq_id} మీకు active quote requestగా లేదు."
        items = self.repository.list_items(rfq_id)
        quote_id = self.repository.start_quote(rfq_id, seller_user_id, delivery_fee=delivery_fee)
        matched = 0
        for item in items:
            item_key = self._norm(item["item_name"])
            price = None
            for key, value in price_map.items():
                if self._similar(item_key, key):
                    price = value
                    break
            if price is not None:
                self.repository.set_item_quote(quote_id, int(item["id"]), price, available=True)
                matched += 1
        if matched == 0:
            return "Quoteలో RFQ itemsకి matching prices దొరకలేదు. Example: GQUOTE 12 rice=300, oil=150, delivery=30"
        self.repository.submit_quote(quote_id)
        buyer_id = str(target["buyer_user_id"])
        buyer = self.contact_resolver(buyer_id) or {}
        buyer_mobile = str(buyer.get("mobile") or buyer.get("phone") or buyer_id)
        ranking = self.ranking.rank(rfq_id, top_n=3)
        best = ranking.get("best_value") or {}
        total = best.get("total")
        total_text = f"₹{float(total):.0f}" if isinstance(total, (int, float)) else "updated"
        self.whatsapp.send_text_message(buyer_mobile, f"🛒 Grocery RFQ #{rfq_id}: కొత్త seller quote వచ్చింది. Current best value total: {total_text}. 'Grocery Quotes' పంపితే comparison చూపిస్తాను.")
        return f"✅ RFQ #{rfq_id} quote submit అయింది. {matched}/{len(items)} items priced."

    def _format_latest_quotes(self, buyer_user_id: str) -> str:
        rfq = self.repository.latest_open_for_buyer(buyer_user_id)
        if not rfq:
            return "మీకు open Grocery RFQ లేదు."
        rfq_id = int(rfq["id"])
        ranking = self.ranking.rank(rfq_id, top_n=3)
        rows = ranking.get("top_sellers") or []
        if not rows:
            return f"🛒 Grocery RFQ #{rfq_id}: ఇంకా seller quotes రాలేదు."
        lines = [f"🛒 Grocery RFQ #{rfq_id} — Top quotes"]
        for index, row in enumerate(rows, start=1):
            coverage = float(row.get("coverage") or 0) * 100
            total = float(row.get("total") or 0)
            lines.append(f"{index}. Seller {row['seller_user_id']} — ₹{total:.0f} — {coverage:.0f}% basket coverage")
        best = ranking.get("best_value") or {}
        lowest = ranking.get("lowest_price") or {}
        if best:
            lines.append(f"🤖 Best Value: Seller {best['seller_user_id']}")
        if lowest:
            lines.append(f"💰 Lowest Price: Seller {lowest['seller_user_id']} — ₹{float(lowest.get('total') or 0):.0f}")
        return "\n".join(lines)

    @classmethod
    def _parse_items(cls, message: str) -> List[Dict[str, Any]]:
        text = str(message or "")
        if ":" in text:
            text = text.split(":", 1)[1]
        else:
            parts = text.split(maxsplit=1)
            text = parts[1] if len(parts) > 1 else ""
        chunks = [chunk.strip() for chunk in re.split(r"[,;\n]+", text) if chunk.strip()]
        result: List[Dict[str, Any]] = []
        pattern = re.compile(r"^(.*?)(?:\s+|^)(\d+(?:\.\d+)?)\s*(kg|kgs|g|gm|l|ltr|litre|litres|ml|pcs|pc|pack|packs)?$", re.IGNORECASE)
        for chunk in chunks:
            match = pattern.match(chunk)
            if match:
                name = " ".join(match.group(1).strip().split())
                if name:
                    result.append({"item_name": name, "quantity": float(match.group(2)), "unit": match.group(3)})
            else:
                name = " ".join(chunk.split())
                if name:
                    result.append({"item_name": name, "quantity": None, "unit": None})
        return result

    @classmethod
    def _parse_quote_message(cls, message: str):
        match = re.match(r"^gquote\s+#?(\d+)\s+(.+)$", str(message or "").strip(), flags=re.IGNORECASE)
        if not match:
            return None
        rfq_id = int(match.group(1)); body = match.group(2)
        price_map: Dict[str, float] = {}; delivery_fee = 0.0
        for part in re.split(r"[,;]+", body):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key_norm = cls._norm(key)
            number = re.sub(r"[^0-9.]", "", value)
            if not number:
                continue
            amount = float(number)
            if key_norm in {"delivery", "delivery fee", "డెలివరీ"}:
                delivery_fee = amount
            else:
                price_map[key_norm] = amount
        return rfq_id, price_map, delivery_fee

    @staticmethod
    def _seller_prompt(rfq_id: int, items: List[Dict[str, Any]]) -> str:
        lines = [f"🛒 PODX Grocery RFQ #{rfq_id}", "Buyer needs:"]
        for item in items:
            qty = "" if item.get("quantity") is None else f" {item['quantity']:g}{item.get('unit') or ''}"
            lines.append(f"• {item['item_name']}{qty}")
        example = ", ".join(f"{item['item_name']}=<price>" for item in items[:4])
        lines.append(f"Reply: GQUOTE {rfq_id} {example}, delivery=<fee>")
        return "\n".join(lines)

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(re.sub(r"[^\w\u0C00-\u0C7F\u0900-\u097F]+", " ", str(value or "").casefold()).split())

    @classmethod
    def _similar(cls, a: str, b: str) -> bool:
        return bool(a and b and (a == b or a in b or b in a))
