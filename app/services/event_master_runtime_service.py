"""WhatsApp runtime for command and natural-language Function/Event Master RFQs."""
from __future__ import annotations

import re
from typing import Optional

from app.services.event_intent_extractor import EventIntentExtractor


class EventMasterRuntimeService:
    PENDING_KEY = "event_intake"

    def __init__(self, event_service, user_repository=None, provider_runtime=None, intent_extractor=None, session_registry=None) -> None:
        self.events = event_service
        self.users = user_repository
        self.provider_runtime = provider_runtime
        self.intent_extractor = intent_extractor or EventIntentExtractor()
        self.sessions = session_registry

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        command_mode = clean.casefold().startswith("event rfq ")
        pending = self._pending(sender_user_id)

        if command_mode:
            parsed = self._parse_command(clean)
            if isinstance(parsed, str):
                return parsed
        elif pending:
            parsed = self.intent_extractor.extract_followup(pending, clean)
            if parsed is None:
                return "🎉 Function details ఇంకా complete కాలేదు. " + self._questions(pending.get("missing") or [])
        else:
            parsed = self.intent_extractor.extract(clean)
            if parsed is None:
                return None

        missing = parsed.get("missing") or []
        if missing:
            self._save_pending(sender_user_id, parsed)
            return "🎉 Function requirement అర్థమైంది. Complete RFQ create చేయడానికి ఇంకా: " + self._questions(missing)

        if self.users is not None:
            user = self.users.find_by_whatsapp_mobile(str(sender_user_id)) or {}
            if int(user.get("registration_complete") or 0) != 1:
                return "ముందుగా PODX registration complete చేయండి."

        event_type = str(parsed.get("event_type") or "Function")
        guests = int(parsed.get("guest_count") or 0)
        location = str(parsed.get("location_text") or "").strip()
        services = list(parsed.get("services") or [])
        event_date = parsed.get("event_date")
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

        self._clear_pending(sender_user_id)
        routing = {"offered": 0, "by_service": {}}
        if self.provider_runtime is not None:
            routing = self.provider_runtime.route_children(result)

        lines = [
            f"✅ Event Master RFQ #{result['master_rfq_id']} create అయింది.",
            f"{event_type} • {guests} guests • {location}",
            "Sub-RFQs:",
        ]
        for row in result["children"]:
            count = int((routing.get("by_service") or {}).get(row["service"], 0))
            lines.append(f"• {row['service']}: #{row['rfq_id']} — {count} provider(s) notified")
        lines.append("ప్రతి serviceకి quotation independently compare/select చేయవచ్చు.")
        return "\n".join(lines)

    def _pending(self, sender_user_id: str) -> dict:
        if self.sessions is None:
            return {}
        value = self.sessions.get(str(sender_user_id)).data.get(self.PENDING_KEY)
        return dict(value) if isinstance(value, dict) else {}

    def _save_pending(self, sender_user_id: str, parsed: dict) -> None:
        if self.sessions is None:
            return
        session = self.sessions.get(str(sender_user_id))
        session.data[self.PENDING_KEY] = dict(parsed)
        self.sessions.save(str(sender_user_id))

    def _clear_pending(self, sender_user_id: str) -> None:
        if self.sessions is None:
            return
        session = self.sessions.get(str(sender_user_id))
        if self.PENDING_KEY in session.data:
            session.data.pop(self.PENDING_KEY, None)
            self.sessions.save(str(sender_user_id))

    @staticmethod
    def _questions(missing) -> str:
        labels = {"guest_count": "ఎంతమంది guests?", "location": "function location ఎక్కడ?", "services": "ఏ services కావాలి?"}
        return " ".join(labels[item] for item in missing if item in labels)

    @staticmethod
    def _parse_command(clean: str):
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
        return {
            "event_type": event_type,
            "guest_count": guests,
            "location_text": parts[2],
            "services": [x.strip() for x in re.split(r"[,;+]", parts[3]) if x.strip()],
            "event_date": parts[4] if len(parts) > 4 and parts[4] else None,
            "missing": [],
        }
