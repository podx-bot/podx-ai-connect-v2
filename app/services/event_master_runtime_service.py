"""WhatsApp runtime for one-message Function/Event Master RFQs."""
from __future__ import annotations

import re
from typing import Optional


class EventMasterRuntimeService:
    def __init__(self, event_service, user_repository=None) -> None:
        self.events = event_service
        self.users = user_repository

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if not clean.casefold().startswith("event rfq "):
            return None
        if self.users is not None:
            user = self.users.find_by_whatsapp_mobile(str(sender_user_id)) or {}
            if int(user.get("registration_complete") or 0) != 1:
                return "ముందుగా PODX registration complete చేయండి."
        payload = clean[len("event rfq "):]
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 4:
            return "Format: EVENT RFQ <FUNCTION> | <GUESTS> | <LOCATION> | <SERVICES> | <DATE optional>"
        event_type = parts[0] or "Function"
        try:
            guests = int(re.sub(r"[^0-9]", "", parts[1]))
        except ValueError:
            guests = 0
        if guests <= 0:
            return "Guest count సరైన numberగా ఇవ్వండి."
        location = parts[2]
        services = [x.strip() for x in re.split(r"[,;+]", parts[3]) if x.strip()]
        event_date = parts[4] if len(parts) > 4 and parts[4] else None
        result = self.events.create_master_event(
            requester_user_id=sender_user_id,
            event_type=event_type,
            guest_count=guests,
            location_text=location,
            services=services,
            event_date=event_date,
        )
        if result.get("status") != "CREATED":
            return "Services గుర్తించలేకపోయాను. Catering, Hall, Decoration, Photography, Flowers, Sound, Transportలో కావాల్సినవి చెప్పండి."
        children = result["children"]
        lines = [f"✅ Event Master RFQ #{result['master_rfq_id']} create అయింది.",
                 f"{event_type} • {guests} guests • {location}", "Sub-RFQs:"]
        lines.extend(f"• {row['service']}: #{row['rfq_id']}" for row in children)
        lines.append("ప్రతి serviceకి quotation independently compare/select చేయవచ్చు.")
        return "\n".join(lines)
