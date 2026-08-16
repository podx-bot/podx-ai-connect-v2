"""Provider targeting, quote lifecycle and final booking for Event Master RFQs."""
from __future__ import annotations

import math
import re
from typing import Optional

from app.services.event_booking_service import EventBookingService
from app.services.event_master_rfq_service import EventMasterRFQService


class EventProviderRuntimeService:
    def __init__(
        self,
        rfq_repository,
        rfq_service,
        marketplace_repository,
        catering_catalog_repository,
        whatsapp_service,
        contact_resolver,
    ) -> None:
        self.rfqs = rfq_repository
        self.rfq_service = rfq_service
        self.marketplace = marketplace_repository
        self.catering = catering_catalog_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.booking = EventBookingService(rfq_repository, whatsapp_service, contact_resolver)

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        lowered = clean.casefold()
        if lowered.startswith("equote "):
            return self._quote(sender_user_id, clean)
        if lowered.startswith("ecompare "):
            return self._compare(sender_user_id, clean)
        if lowered.startswith("eselect "):
            return self._select(sender_user_id, clean)
        if lowered.startswith("esummary "):
            return self._summary(sender_user_id, clean)
        if lowered.startswith("ebook "):
            return self._book(sender_user_id, clean)
        return None

    def route_children(self, event_result: dict) -> dict:
        offered = 0
        by_service = {}
        for child in event_result.get("children") or []:
            service_type = str(child.get("service") or "").upper()
            rfq_id = int(child["rfq_id"])
            count = self._route_child(rfq_id, service_type)
            offered += count
            by_service[service_type] = count
        return {"offered": offered, "by_service": by_service}

    def _route_child(self, rfq_id: int, service_type: str) -> int:
        rfq = self.rfqs.get_rfq(rfq_id) or {}
        requester_id = str(rfq.get("requester_user_id") or "")
        requester = self.contact_resolver(requester_id) or {}
        candidates = []
        if service_type == "CATERING":
            for row in self.catering.list_active_providers(limit=30):
                candidates.append({"provider_user_id": str(row["provider_user_id"]), "service_name": "Catering"})
        else:
            aliases = [service_type]
            aliases.extend(EventMasterRFQService.SERVICE_ALIASES.get(service_type, ()))
            for row in self.marketplace.find_service_providers(aliases, limit=30):
                candidates.append({"provider_user_id": str(row["provider_mobile"]), "service_name": row.get("service_name")})

        ranked = []
        for candidate in candidates:
            provider_id = str(candidate["provider_user_id"])
            if not provider_id or provider_id == requester_id:
                continue
            provider = self.contact_resolver(provider_id) or {}
            distance = self._distance_km(
                requester.get("latitude"), requester.get("longitude"),
                provider.get("latitude"), provider.get("longitude"),
            )
            ranked.append((distance if distance is not None else 9999.0, provider_id, provider, distance))
        ranked.sort(key=lambda row: (row[0], row[1]))

        sent = 0
        metadata = rfq.get("metadata") or {}
        event_type = str(metadata.get("event_type") or "Function")
        for _, provider_id, provider, distance in ranked[:20]:
            if not self.rfqs.add_target(rfq_id, provider_id, match_score=1.0, distance_km=distance):
                continue
            distance_text = f"\nDistance: {distance:.1f} km" if distance is not None else ""
            body = (
                f"🎉 PODX Event RFQ #{rfq_id}\n"
                f"Service: {service_type.title()}\n"
                f"Event: {event_type}\n"
                f"Guests: {rfq.get('guest_count') or '-'}\n"
                f"Location: {rfq.get('location_text') or '-'}\n"
                f"Date: {rfq.get('event_date') or '-'}{distance_text}\n"
                f"Quotation పంపడానికి: EQUOTE {rfq_id} <TOTAL AMOUNT>"
            )
            self.whatsapp.send_text_message(str(provider.get("mobile") or provider_id), body)
            sent += 1
        return sent

    def _quote(self, provider_user_id: str, message: str) -> str:
        match = re.match(r"^equote\s+#?(\d+)\s+([0-9,.]+)$", message, re.I)
        if not match:
            return "Format: EQUOTE <RFQ ID> <TOTAL AMOUNT>"
        rfq_id = int(match.group(1))
        total = float(match.group(2).replace(",", ""))
        if total <= 0:
            return "Quotation amount 0 కంటే ఎక్కువ ఉండాలి."
        target = self.rfqs.target_for_provider(provider_user_id, rfq_id)
        if not target:
            return f"Event RFQ #{rfq_id} మీకు active quotation requestగా లేదు."
        rfq = self.rfqs.get_rfq(rfq_id) or {}
        metadata = rfq.get("metadata") or {}
        if not metadata.get("master_event_rfq_id"):
            return f"RFQ #{rfq_id} Event child RFQ కాదు."
        quote_id = self.rfqs.start_quote(rfq_id, provider_user_id, provider_total=total)
        for item in self.rfqs.list_items(rfq_id):
            self.rfqs.set_item_quote(quote_id, int(item["id"]), available=True, included=True)
        self.rfqs.submit_quote(quote_id)
        buyer = self.contact_resolver(str(rfq.get("requester_user_id") or "")) or {}
        service_type = str(metadata.get("service_type") or "Service").title()
        self.whatsapp.send_text_message(
            str(buyer.get("mobile") or rfq.get("requester_user_id")),
            f"🎉 New {service_type} quote for Event RFQ #{rfq_id}\nProvider: {provider_user_id}\nTotal: ₹{total:.0f}\nCompare: ECOMPARE {rfq_id}",
        )
        return f"✅ Event Quote #{quote_id} submit అయింది. Total ₹{total:.0f}."

    def _compare(self, requester_user_id: str, message: str) -> str:
        match = re.match(r"^ecompare\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: ECOMPARE <RFQ ID>"
        rfq_id = int(match.group(1))
        rfq = self.rfqs.get_rfq(rfq_id)
        if not rfq or str(rfq.get("requester_user_id")) != str(requester_user_id):
            return f"Event RFQ #{rfq_id} మీ RFQ కాదు."
        metadata = rfq.get("metadata") or {}
        if not metadata.get("master_event_rfq_id"):
            return f"RFQ #{rfq_id} Event child RFQ కాదు."
        result = self.rfq_service.compare_quotes(rfq_id)
        quotes = result.get("quotes") or []
        if not quotes:
            return f"Event RFQ #{rfq_id}కి submitted quotations ఇంకా లేవు."
        service_type = str(metadata.get("service_type") or "Service").title()
        lines = [f"🎉 {service_type} RFQ #{rfq_id} Quote Comparison"]
        for row in quotes[:8]:
            lines.append(f"#{row['quote_id']} {row['provider_user_id']} — ₹{row['total']:.0f} — {row['label']}")
        lines.append("Select: ESELECT <RFQ ID> <QUOTE ID>")
        return "\n".join(lines)

    def _select(self, requester_user_id: str, message: str) -> str:
        match = re.match(r"^eselect\s+#?(\d+)\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: ESELECT <RFQ ID> <QUOTE ID>"
        rfq_id, quote_id = int(match.group(1)), int(match.group(2))
        rfq = self.rfqs.get_rfq(rfq_id)
        if not rfq or str(rfq.get("requester_user_id")) != str(requester_user_id):
            return f"Event RFQ #{rfq_id} మీ RFQ కాదు."
        metadata = rfq.get("metadata") or {}
        if not metadata.get("master_event_rfq_id"):
            return f"RFQ #{rfq_id} Event child RFQ కాదు."
        result = self.rfq_service.select_quote(rfq_id, quote_id, requester_user_id)
        if result.get("status") != "SELECTED":
            return f"Event quote select చేయలేకపోయాను. Status: {result.get('status')}"
        provider_id = str(result.get("provider_user_id") or "")
        provider = self.contact_resolver(provider_id) or {}
        service_type = str(metadata.get("service_type") or "Service").title()
        self.whatsapp.send_text_message(
            str(provider.get("mobile") or provider_id),
            f"✅ మీ {service_type} Quote #{quote_id} Event RFQ #{rfq_id}కి select అయింది. Final booking confirmation కోసం wait చేయండి.",
        )
        master_id = int(metadata.get("master_event_rfq_id"))
        return (
            f"✅ {service_type} Quote #{quote_id} select అయింది. Provider {provider_id}. Total ₹{float(result.get('total') or 0):.0f}.\n"
            f"Full Event package చూడటానికి: ESUMMARY {master_id}"
        )

    def _summary(self, requester_user_id: str, message: str) -> str:
        match = re.match(r"^esummary\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: ESUMMARY <MASTER EVENT RFQ ID>"
        master_id = int(match.group(1))
        result = self.booking.package_summary(master_id, requester_user_id)
        if result.get("status") == "MASTER_NOT_FOUND":
            return f"Master Event RFQ #{master_id} దొరకలేదు."
        if result.get("status") == "NOT_OWNER":
            return f"Master Event RFQ #{master_id} మీది కాదు."
        master = result["master"]
        lines = [
            f"🎉 Event Package Summary #{master_id}",
            f"{master.get('title') or 'Function'}",
            f"Date: {master.get('event_date') or '-'}",
            f"Location: {master.get('location_text') or '-'}",
            "Selected services:",
        ]
        if result["selected"]:
            for row in result["selected"]:
                lines.append(f"• {row['service']}: {row['provider_user_id']} — ₹{row['total']:.0f}")
        else:
            lines.append("• ఇంకా ఏ service select కాలేదు")
        if result["missing"]:
            lines.append("Pending: " + ", ".join(result["missing"]))
        lines.append(f"Combined selected total: ₹{result['combined_total']:.0f}")
        if result["ready_to_book"]:
            lines.append(f"Final booking: EBOOK {master_id}")
        else:
            lines.append("అన్ని requested services select చేసిన తర్వాత final booking చేయవచ్చు.")
        return "\n".join(lines)

    def _book(self, requester_user_id: str, message: str) -> str:
        match = re.match(r"^ebook\s+#?(\d+)$", message, re.I)
        if not match:
            return "Format: EBOOK <MASTER EVENT RFQ ID>"
        master_id = int(match.group(1))
        result = self.booking.confirm_booking(master_id, requester_user_id)
        status = result.get("status")
        if status == "MASTER_NOT_FOUND":
            return f"Master Event RFQ #{master_id} దొరకలేదు."
        if status == "NOT_OWNER":
            return f"Master Event RFQ #{master_id} మీది కాదు."
        if status == "INCOMPLETE_SELECTION":
            return "Final bookingకి ముందు ఇంకా select చేయాల్సిన services: " + ", ".join(result.get("missing") or [])
        if status == "ALREADY_BOOKED":
            return f"✅ Event #{master_id} ఇప్పటికే booked అయింది. Combined total ₹{result['combined_total']:.0f}."
        if status != "BOOKED":
            return f"Event booking complete చేయలేకపోయాను. Status: {status}"
        return (
            f"✅ Event Booking Confirmed #{master_id}\n"
            f"{len(result['selected'])} services confirmed\n"
            f"Combined total: ₹{result['combined_total']:.0f}\n"
            f"Selected providersకి final confirmation పంపబడింది."
        )

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
