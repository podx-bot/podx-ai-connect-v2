"""Master Event RFQ orchestration on top of the Universal RFQ repository."""
from __future__ import annotations

from typing import Any


class EventMasterRFQService:
    """Split one function/event need into independently quotable local service RFQs."""

    SERVICE_ALIASES = {
        "CATERING": ("catering", "food", "menu", "కేటరింగ్", "భోజనం", "ఫుడ్"),
        "HALL": ("hall", "venue", "function hall", "ఫంక్షన్ హాల్", "హాల్", "వేదిక"),
        "DECORATION": ("decoration", "decor", "stage", "డెకరేషన్", "స్టేజ్"),
        "PHOTOGRAPHY": ("photography", "photo", "video", "photographer", "ఫోటోగ్రఫీ", "ఫోటో", "వీడియో"),
        "FLOWERS": ("flowers", "flower", "garland", "ఫ్లవర్స్", "పూలు", "దండలు"),
        "SOUND": ("sound", "dj", "music", "audio", "సౌండ్", "డీజే", "మ్యూజిక్"),
        "TRANSPORT": ("transport", "bus", "car", "vehicle", "ట్రాన్స్‌పోర్ట్", "బస్", "కార్", "వాహనం"),
    }

    def __init__(self, rfq_repository) -> None:
        self.rfqs = rfq_repository

    def create_master_event(
        self,
        requester_user_id: str,
        event_type: str,
        guest_count: int,
        location_text: str,
        services: list[str],
        event_date: str | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_services(services)
        if not normalized:
            return {"status": "NO_SERVICES", "children": []}

        master_id = self.rfqs.create_rfq(
            requester_user_id=requester_user_id,
            rfq_type="EVENT",
            title=f"{event_type or 'Function'} for {guest_count} guests",
            location_text=location_text,
            event_date=event_date,
            guest_count=guest_count,
            metadata={"event_type": event_type or "Function", "services": normalized},
            items=[{"name": service, "quantity": 1, "unit": "service", "required": True} for service in normalized],
        )

        children = []
        for service in normalized:
            child_kind = "CATERING" if service == "CATERING" else "SERVICE"
            child_id = self.rfqs.create_rfq(
                requester_user_id=requester_user_id,
                rfq_type=child_kind,
                title=f"{service.title()} for {event_type or 'Function'}",
                location_text=location_text,
                event_date=event_date,
                guest_count=guest_count,
                metadata={
                    "master_event_rfq_id": master_id,
                    "service_type": service,
                    "event_type": event_type or "Function",
                },
                items=[{
                    "name": service,
                    "category": service,
                    "quantity": guest_count if service == "CATERING" else 1,
                    "unit": "guest" if service == "CATERING" else "service",
                    "required": True,
                }],
            )
            children.append({"service": service, "rfq_id": child_id, "rfq_type": child_kind})
        return {"status": "CREATED", "master_rfq_id": master_id, "children": children}

    @classmethod
    def normalize_services(cls, services: list[str]) -> list[str]:
        result: list[str] = []
        for raw in services:
            text = " ".join(str(raw or "").casefold().strip().split())
            if not text:
                continue
            matched = None
            for service, aliases in cls.SERVICE_ALIASES.items():
                if text == service.casefold() or any(alias in text for alias in aliases):
                    matched = service
                    break
            if matched and matched not in result:
                result.append(matched)
        return result
