"""Provider matching and first-confirm appointment handoff."""
from __future__ import annotations

import re
from typing import Any


class AppointmentProviderRuntimeService:
    CATEGORY_ALIASES = {
        "Doctor": ["doctor", "డాక్టర్", "physician"],
        "Hospital/Clinic": ["hospital", "clinic", "హాస్పిటల్", "క్లినిక్", "doctor"],
        "Salon": ["salon", "hair salon", "barber", "సెలూన్"],
        "Beauty Parlour": ["beauty parlour", "beauty parlor", "beautician", "parlour", "బ్యూటీ పార్లర్"],
        "Other": [],
    }

    def __init__(self, appointment_repository, marketplace_repository, whatsapp_service, user_repository=None) -> None:
        self.appointments = appointment_repository
        self.marketplace = marketplace_repository
        self.whatsapp = whatsapp_service
        self.users = user_repository

    def notify_matching_providers(self, request: dict[str, Any]) -> dict[str, Any]:
        aliases = self.CATEGORY_ALIASES.get(str(request.get("category") or ""), [])
        if not aliases:
            aliases = [str(request.get("category") or "")]
        providers = self.marketplace.find_service_providers(aliases, limit=30)
        sent = 0
        for provider in providers:
            if not self._area_matches(request.get("area"), provider.get("area")):
                continue
            mobile = str(provider.get("provider_mobile") or "").strip()
            if not mobile:
                continue
            result = self.whatsapp.send_text_message(
                mobile,
                "📅 PODX Appointment Request\n"
                f"Request: #{request['id']}\n"
                f"Type: {request['category']}\n"
                f"Area/Place: {request['area']}\n"
                f"Date: {request['preferred_date']}\n"
                f"Time: {request['preferred_time']}\n\n"
                f"Accept చేయాలంటే: APPT ACCEPT {request['id']}\n"
                f"వద్దంటే: APPT DECLINE {request['id']}",
            )
            if bool((result or {}).get("success")):
                sent += 1
        return {"status": "NOTIFIED" if sent else "NO_PROVIDER", "sent": sent}

    def process_provider_command(self, sender_mobile: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        match = re.fullmatch(r"(?i)APPT\s+(ACCEPT|DECLINE|DONE)\s+(\d+)", clean)
        if not match:
            return None
        action = match.group(1).upper()
        request_id = int(match.group(2))
        request = self.appointments.get_request(request_id)
        if not request:
            return f"Appointment request #{request_id} దొరకలేదు."

        if action == "DECLINE":
            return f"సరే. Appointment #{request_id} decline చేశాను."

        if not self._provider_is_eligible(sender_mobile, request):
            return "ఈ appointment మీ saved service/profileకి match కావడం లేదు."

        if action == "DONE":
            if self.appointments.mark_completed(request_id, sender_mobile):
                customer = self._customer_mobile(request)
                self.whatsapp.send_text_message(
                    customer,
                    f"✅ Appointment #{request_id} provider completed అని mark చేశారు. Thank you for using PODX.",
                )
                return f"✅ Appointment #{request_id} completedగా mark అయింది."
            return "ఈ appointment మీకు assigned కాలేదు లేదా ఇప్పటికే close అయింది."

        if self.appointments.claim_provider(request_id, sender_mobile):
            customer = self._customer_mobile(request)
            provider_name = self._provider_name(sender_mobile)
            self.whatsapp.send_text_message(
                customer,
                "✅ మీ appointment confirm అయింది.\n"
                f"Request: #{request_id}\n"
                f"Provider: {provider_name}\n"
                f"Type: {request['category']}\n"
                f"Date: {request['preferred_date']}\n"
                f"Time: {request['preferred_time']}\n"
                f"Place: {request['area']}",
            )
            return (
                f"✅ Appointment #{request_id} మీకు assign అయింది.\n"
                "Customerకి confirmation పంపాను. Service పూర్తయ్యాక "
                f"APPT DONE {request_id} పంపండి."
            )

        assigned = self.appointments.get_assignment(request_id)
        if assigned and str(assigned.get("provider_mobile")) == str(sender_mobile):
            return f"✅ Appointment #{request_id} ఇప్పటికే మీకు confirmed అయింది."
        return f"Appointment #{request_id} ఇప్పటికే మరో provider confirm చేశారు."

    def _provider_is_eligible(self, provider_mobile: str, request: dict[str, Any]) -> bool:
        aliases = self.CATEGORY_ALIASES.get(str(request.get("category") or ""), [])
        if not aliases:
            aliases = [str(request.get("category") or "")]
        providers = self.marketplace.find_service_providers(aliases, limit=100)
        for provider in providers:
            if str(provider.get("provider_mobile")) != str(provider_mobile):
                continue
            if self._area_matches(request.get("area"), provider.get("area")):
                return True
        return False

    def _customer_mobile(self, request: dict[str, Any]) -> str:
        user_id = str(request.get("customer_mobile") or "")
        if self.users is None:
            return user_id
        user = self.users.find_by_whatsapp_mobile(user_id) or {}
        return str(user.get("whatsapp_mobile") or user_id)

    def _provider_name(self, provider_mobile: str) -> str:
        if self.users is None:
            return "Matched provider"
        user = self.users.find_by_whatsapp_mobile(str(provider_mobile)) or {}
        return str(user.get("business_name") or user.get("name") or "Matched provider")

    @staticmethod
    def _area_matches(request_area: Any, provider_area: Any) -> bool:
        request_text = " ".join(str(request_area or "").casefold().strip().split())
        provider_text = " ".join(str(provider_area or "").casefold().strip().split())
        if request_text in {"", "nearby", "near me"}:
            return True
        if not provider_text:
            return True
        return request_text in provider_text or provider_text in request_text
