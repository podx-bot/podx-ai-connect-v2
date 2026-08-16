"""WhatsApp Catering Catalog + RFQ runtime on the Universal RFQ foundation."""
from __future__ import annotations

import math
import re
from typing import Any, Optional


class CateringRFQRuntimeService:
    def __init__(
        self,
        catalog_repository,
        rfq_repository,
        rfq_service,
        whatsapp_service,
        contact_resolver,
        user_repository=None,
    ) -> None:
        self.catalog = catalog_repository
        self.rfqs = rfq_repository
        self.rfq_service = rfq_service
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if lowered == "caterer on":
            return self._enable_caterer(sender_user_id)
        if lowered.startswith("cmenu "):
            return self._save_menu(sender_user_id, clean[6:])
        if lowered == "clist":
            return self._list_menu(sender_user_id)
        if lowered.startswith("crfq "):
            return self._create_rfq(sender_user_id, clean[5:])
        if lowered.startswith("cquote "):
            return self._quote(sender_user_id, clean)
        if lowered.startswith("ccompare "):
            return self._compare(sender_user_id, clean)
        if lowered.startswith("cselect "):
            return self._select(sender_user_id, clean)
        return None

    def _enable_caterer(self, provider_user_id: str) -> str:
        if not self._registered(provider_user_id):
            return "Catererగా join అవ్వడానికి ముందుగా PODX registration complete చేయండి."
        contact = self.contact_resolver(provider_user_id) or {}
        self.catalog.enable_provider(provider_user_id, contact.get("business_name") or contact.get("name"))
        if self.users is not None:
            self.users.add_capability(provider_user_id, "SERVICE_PROVIDER", source="catering_runtime")
        return "✅ Catering profile ON. మీ menu/items పంపండి: CMENU Chicken Biryani, Paneer Curry, Sweet, Serving Staff"

    def _save_menu(self, provider_user_id: str, raw_items: str) -> str:
        if not self._registered(provider_user_id):
            return "ముందుగా PODX registration complete చేయండి."
        items = self._split_items(raw_items)
        if not items:
            return "Format: CMENU <item 1>, <item 2>, <item 3>"
        count = self.catalog.add_items(provider_user_id, items, source="text_or_voice")
        return f"✅ మీ Catering Catalogలో {count} item(s) save అయ్యాయి. Total active items: {len(self.catalog.list_items(provider_user_id))}."

    def _list_menu(self, provider_user_id: str) -> str:
        items = self.catalog.list_items(provider_user_id)
        if not items:
            return "మీ Catering Catalog ఇంకా emptyగా ఉంది. CMENU <items> పంపండి."
        names = [str(item.get("item_name")) for item in items[:40]]
        extra = f"\n+{len(items)-40} more" if len(items) > 40 else ""
        return "🍽️ మీ Catering Catalog:\n• " + "\n• ".join(names) + extra

    def _create_rfq(self, buyer_user_id: str, payload: str) -> str:
        if not self._registered(buyer_user_id):
            return "ముందుగా PODX registration complete చేయండి."
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 3:
            return "Format: CRFQ <GUESTS> | <LOCATION> | <ITEM 1>, <ITEM 2>, ..."
        try:
            guests = int(re.sub(r"[^0-9]", "", parts[0]))
        except ValueError:
            guests = 0
        if guests <= 0:
            return "Guest count సరైన numberగా ఇవ్వండి. Example: CRFQ 300 | Vijayawada | Chicken Biryani, Sweet"
        location = parts[1]
        names = self._split_items(" | ".join(parts[2:]))
        if not names:
            return "Catering RFQకి కనీసం ఒక item కావాలి."
        items = [{"name": name, "quantity": guests, "unit": "guest", "required": True} for name in names]
        rfq_id = self.rfqs.create_rfq(
            requester_user_id=buyer_user_id,
            rfq_type="CATERING",
            title=f"Catering for {guests} guests",
            location_text=location,
            guest_count=guests,
            items=items,
        )
        matches = self._target_caterers(rfq_id, buyer_user_id, items)
        if matches:
            return f"✅ Catering RFQ #{rfq_id} create అయింది. {len(names)} items, {guests} guests. {matches} matching caterer(s)కి quotation request పంపాను."
        return f"✅ Catering RFQ #{rfq_id} create అయింది. ప్రస్తుతం matching catalog ఉన్న caterer దొరకలేదు; RFQ OPENగా ఉంచాను."

    def _target_caterers(self, rfq_id: int, buyer_user_id: str, items: list[dict]) -> int:
        candidates = self.catalog.find_matching_providers(items, limit=30)
        buyer = self.contact_resolver(buyer_user_id) or {}
        ranked = []
        for candidate in candidates:
            provider_id = str(candidate["provider_user_id"])
            if provider_id == str(buyer_user_id):
                continue
            contact = self.contact_resolver(provider_id) or {}
            distance = self._distance_km(
                buyer.get("latitude"), buyer.get("longitude"), contact.get("latitude"), contact.get("longitude")
            )
            ranked.append((distance if distance is not None else 9999.0, -float(candidate.get("match_percent") or 0), candidate, contact, distance))
        ranked.sort(key=lambda row: (row[0], row[1], str(row[2]["provider_user_id"])))
        sent = 0
        requested = self.rfqs.list_items(rfq_id)
        request_text = ", ".join(str(item["item_name"]) for item in requested[:12])
        rfq = self.rfqs.get_rfq(rfq_id) or {}
        for _, _, candidate, contact, distance in ranked[:20]:
            provider_id = str(candidate["provider_user_id"])
            score = float(candidate.get("match_percent") or 0) / 100.0
            if not self.rfqs.add_target(rfq_id, provider_id, match_score=score, distance_km=distance):
                continue
            distance_text = f"\nDistance: {distance:.1f} km" if distance is not None else ""
            body = (
                f"🍽️ PODX Catering RFQ #{rfq_id}\n"
                f"Guests: {rfq.get('guest_count') or '-'}\nLocation: {rfq.get('location_text') or '-'}\n"
                f"Requested: {request_text}\n"
                f"Your catalog match: {candidate.get('matched_items')}/{candidate.get('requested_items')} ({candidate.get('match_percent')}%)"
                f"{distance_text}\n"
                f"Quote పంపడానికి: CQUOTE {rfq_id} <TOTAL AMOUNT>"
            )
            mobile = str(contact.get("mobile") or provider_id)
            self.whatsapp.send_text_message(mobile, body)
            sent += 1
        return sent

    def _quote(self, provider_user_id: str, message: str) -> str:
        match = re.match(r"^cquote\s+#?(\d+)\s+([0-9,.]+)$", message, re.I)
        if not match:
            return "Format: CQUOTE <RFQ ID> <TOTAL AMOUNT>"
        rfq_id = int(match.group(1))
        total = float(match.group(2).replace(",", ""))
        target = self.rfqs.target_for_provider(provider_user_id, rfq_id)
        if not target:
            return f"Catering RFQ #{rfq_id} మీకు active quotation requestగా లేదు."
        quote_id = self.rfqs.start_quote(rfq_id, provider_user_id, provider_total=total)
        requested = self.rfqs.list_items(rfq_id)
        available_count = 0
        missing = []
        for item in requested:
            available = self.catalog.catalog_covers(provider_user_id, str(item["item_name"]))
            self.rfqs.set_item_quote(quote_id, int(item["id"]), available=available, included=available)
            if available:
                available_count += 1
            else:
                missing.append(str(item["item_name"]))
        self.rfqs.submit_quote(quote_id)
        comparison = self.rfq_service.compare_quotes(rfq_id)
        own = next((row for row in comparison.get("quotes", []) if int(row["quote_id"]) == quote_id), {})
        rfq = self.rfqs.get_rfq(rfq_id) or {}
        buyer = self.contact_resolver(str(rfq.get("requester_user_id") or "")) or {}
        missing_text = ", ".join(missing[:8]) if missing else "None"
        self.whatsapp.send_text_message(
            str(buyer.get("mobile") or rfq.get("requester_user_id")),
            f"🍽️ New Catering Quote for RFQ #{rfq_id}\nProvider: {provider_user_id}\nTotal: ₹{total:.0f}\nItems: {available_count}/{len(requested)} ({own.get('coverage_percent', 0)}%)\nMissing: {missing_text}\nCompare: CCOMPARE {rfq_id}",
        )
        return f"✅ Quote #{quote_id} submit అయింది. ₹{total:.0f}. Item coverage {available_count}/{len(requested)}."

    def _compare(self, buyer_user_id: str, message: str) -> str:
        match = re.match(r"^ccompare\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: CCOMPARE <RFQ ID>"
        rfq_id = int(match.group(1))
        rfq = self.rfqs.get_rfq(rfq_id)
        if not rfq or str(rfq.get("requester_user_id")) != str(buyer_user_id):
            return f"Catering RFQ #{rfq_id} మీ RFQ కాదు."
        result = self.rfq_service.compare_quotes(rfq_id)
        quotes = result.get("quotes") or []
        if not quotes:
            return f"RFQ #{rfq_id}కి submitted quotations ఇంకా లేవు."
        lines = [f"🍽️ Catering RFQ #{rfq_id} Quote Comparison"]
        for row in quotes[:6]:
            missing = ", ".join(row.get("missing_items") or []) or "None"
            lines.append(
                f"#{row['quote_id']} {row['provider_user_id']} — ₹{row['total']:.0f} — {row['coverage_percent']}% match — Missing: {missing}"
            )
        lines.append("Select: CSELECT <RFQ ID> <QUOTE ID>")
        return "\n".join(lines)

    def _select(self, buyer_user_id: str, message: str) -> str:
        match = re.match(r"^cselect\s+#?(\d+)\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: CSELECT <RFQ ID> <QUOTE ID>"
        rfq_id, quote_id = int(match.group(1)), int(match.group(2))
        result = self.rfq_service.select_quote(rfq_id, quote_id, buyer_user_id)
        if result.get("status") != "SELECTED":
            return f"Catering quote select చేయలేకపోయాను. Status: {result.get('status')}"
        provider_id = str(result.get("provider_user_id") or "")
        provider = self.contact_resolver(provider_id) or {}
        self.whatsapp.send_text_message(
            str(provider.get("mobile") or provider_id),
            f"✅ మీ Catering Quote #{quote_id} RFQ #{rfq_id}కి select అయింది. Buyer confirmation/order handoff next stepకి ready.",
        )
        return f"✅ Catering Quote #{quote_id} select అయింది. Provider {provider_id}. Total ₹{float(result.get('total') or 0):.0f}."

    def _registered(self, user_id: str) -> bool:
        if self.users is None:
            return True
        user = self.users.find_by_whatsapp_mobile(str(user_id)) or {}
        return int(user.get("registration_complete") or 0) == 1

    @staticmethod
    def _split_items(value: Any) -> list[str]:
        text = str(value or "").replace(";", ",").replace("\n", ",")
        result = []
        seen = set()
        for part in text.split(","):
            clean = " ".join(part.strip().split())
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    @staticmethod
    def _distance_km(lat1, lon1, lat2, lon2):
        if None in {lat1, lon1, lat2, lon2}:
            return None
        try:
            p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
            dlat = p2 - p1
            dlon = math.radians(float(lon2) - float(lon1))
            a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
            return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        except (TypeError, ValueError):
            return None
