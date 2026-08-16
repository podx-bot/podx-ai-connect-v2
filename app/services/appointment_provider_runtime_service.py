"""Provider matching plus two-sided appointment confirmation lifecycle."""
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
    CUSTOMER_CONFIRM_WORDS = {
        "confirm appointment", "appointment confirm", "confirm my appointment",
        "అపాయింట్మెంట్ కన్ఫర్మ్", "అపాయింట్మెంట్ కన్‌ఫర్మ్", "కన్ఫర్మ్ అపాయింట్మెంట్",
    }
    CUSTOMER_CANCEL_WORDS = {
        "cancel appointment", "appointment cancel", "cancel my appointment",
        "అపాయింట్మెంట్ క్యాన్సిల్", "క్యాన్సిల్ అపాయింట్మెంట్",
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
        """Compatibility entrypoint used by MarketplaceConversationService.

        It now handles both provider and customer appointment lifecycle commands.
        """
        clean = " ".join(str(message or "").strip().split())
        normalized = clean.casefold()

        match = re.fullmatch(r"APPT\s+(ACCEPT|DECLINE|DONE)\s+(\d+)", clean, re.IGNORECASE)
        if match:
            return self._provider_action(sender_mobile, match.group(1).upper(), int(match.group(2)))

        match = re.fullmatch(r"APPT\s+RESCHEDULE\s+(ACCEPT|DECLINE)\s+(\d+)", clean, re.IGNORECASE)
        if match:
            return self._provider_reschedule_action(sender_mobile, match.group(1).upper(), int(match.group(2)))

        match = re.fullmatch(r"APPT\s+CONFIRM\s+(\d+)", clean, re.IGNORECASE)
        if match:
            return self._customer_confirm(sender_mobile, int(match.group(1)))

        match = re.fullmatch(r"APPT\s+CANCEL\s+(\d+)", clean, re.IGNORECASE)
        if match:
            return self._customer_cancel(sender_mobile, int(match.group(1)))

        match = re.fullmatch(r"APPT\s+STATUS(?:\s+(\d+))?", clean, re.IGNORECASE)
        if match:
            request_id = int(match.group(1)) if match.group(1) else None
            return self._status(sender_mobile, request_id)

        match = re.fullmatch(r"APPT\s+RESCHEDULE\s+(\d+)\s*\|\s*(.+?)\s*\|\s*(.+)", clean, re.IGNORECASE)
        if match:
            return self._customer_reschedule(
                sender_mobile,
                int(match.group(1)),
                match.group(2).strip(),
                match.group(3).strip(),
            )

        if normalized in self.CUSTOMER_CONFIRM_WORDS:
            request = self.appointments.latest_customer_request(sender_mobile, statuses=("PROVIDER_ACCEPTED",))
            if request:
                return self._customer_confirm(sender_mobile, int(request["id"]))
            return None

        if normalized in self.CUSTOMER_CANCEL_WORDS:
            request = self.appointments.latest_customer_request(sender_mobile)
            if request:
                return self._customer_cancel(sender_mobile, int(request["id"]))
            return None

        if normalized in {"appointment status", "my appointment status", "అపాయింట్మెంట్ స్టేటస్"}:
            return self._status(sender_mobile, None)

        if normalized.startswith("reschedule ") or normalized.startswith("అపాయింట్మెంట్ మార్చు "):
            request = self.appointments.latest_customer_request(
                sender_mobile,
                statuses=("PROVIDER_ACCEPTED", "CONFIRMED"),
            )
            if not request:
                return None
            schedule_text = clean.split(" ", 1)[1] if " " in clean else ""
            preferred_date, preferred_time = self._extract_schedule(schedule_text)
            if not preferred_date or not preferred_time:
                return "కొత్త రోజు + సమయం చెప్పండి. ఉదా: Reschedule Tomorrow 4 PM."
            return self._customer_reschedule(
                sender_mobile,
                int(request["id"]),
                preferred_date,
                preferred_time,
            )
        return None

    def _provider_action(self, sender_mobile: str, action: str, request_id: int) -> str:
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
            return "ఈ appointment మీకు final confirmed కాలేదు లేదా ఇప్పటికే close అయింది."

        if self.appointments.claim_provider(request_id, sender_mobile):
            customer = self._customer_mobile(request)
            provider_name = self._provider_name(sender_mobile)
            self.whatsapp.send_text_message(
                customer,
                "✅ ఒక provider మీ appointment request accept చేశారు.\n"
                f"Request: #{request_id}\n"
                f"Provider: {provider_name}\n"
                f"Type: {request['category']}\n"
                f"Date: {request['preferred_date']}\n"
                f"Time: {request['preferred_time']}\n"
                f"Place: {request['area']}\n\n"
                f"Final confirm చేయాలంటే: APPT CONFIRM {request_id}\n"
                f"వద్దంటే: APPT CANCEL {request_id}",
            )
            return (
                f"✅ Appointment #{request_id} మీరు accept చేశారు.\n"
                "Customer final confirmation కోసం wait చేస్తున్నాం. "
                "Final confirm అయ్యే వరకు contact details share కావు."
            )

        assigned = self.appointments.get_assignment(request_id)
        if assigned and str(assigned.get("provider_mobile")) == str(sender_mobile):
            status = str(assigned.get("status") or "")
            return f"✅ Appointment #{request_id} ఇప్పటికే మీకు assigned అయింది. Status: {status}."
        return f"Appointment #{request_id} ఇప్పటికే మరో provider accept చేశారు."

    def _customer_confirm(self, customer_mobile: str, request_id: int) -> str:
        request = self.appointments.get_request(request_id)
        if not request or str(request.get("customer_mobile")) != str(customer_mobile):
            return "ఈ appointment మీది కాదు లేదా దొరకలేదు."
        assignment = self.appointments.get_assignment(request_id)
        if not assignment:
            return "ఇంకా provider accept చేయలేదు. Provider accept చేసిన తర్వాత final confirm చేయండి."
        already = str(request.get("status") or "").upper() == "CONFIRMED" and bool(assignment.get("customer_confirmed_at"))
        if not self.appointments.customer_confirm(request_id, customer_mobile):
            return "ఈ appointment ఇప్పుడు confirm చేయలేరు. Current status: " + str(request.get("status") or "UNKNOWN")
        provider_mobile = str(assignment["provider_mobile"])
        provider_name = self._provider_name(provider_mobile)
        provider_contact = self._contact(provider_mobile)
        customer_contact = self._contact(customer_mobile)
        if not already:
            self.whatsapp.send_text_message(
                provider_mobile,
                "🎉 Appointment final confirmed.\n"
                f"Request: #{request_id}\n"
                f"Customer contact: {customer_contact}\n"
                f"Date: {request['preferred_date']}\nTime: {request['preferred_time']}\n"
                f"Place: {request['area']}\n\n"
                f"Service పూర్తయ్యాక APPT DONE {request_id} పంపండి.",
            )
        return (
            f"🎉 Appointment #{request_id} final confirmed.\n"
            f"Provider: {provider_name}\n"
            f"Provider contact: {provider_contact}\n"
            f"Date: {request['preferred_date']}\nTime: {request['preferred_time']}\n"
            f"Place: {request['area']}"
        )

    def _customer_cancel(self, customer_mobile: str, request_id: int) -> str:
        request = self.appointments.get_request(request_id)
        if not request or str(request.get("customer_mobile")) != str(customer_mobile):
            return "ఈ appointment మీది కాదు లేదా దొరకలేదు."
        was_cancelled = str(request.get("status") or "").upper() == "CANCELLED"
        assignment = self.appointments.get_assignment(request_id)
        if not self.appointments.cancel_request(request_id, customer_mobile):
            return "Completed/closed appointmentని cancel చేయలేరు."
        if assignment and not was_cancelled:
            self.whatsapp.send_text_message(
                str(assignment["provider_mobile"]),
                f"ℹ️ Appointment #{request_id} customer cancel చేశారు.",
            )
        return f"✅ Appointment #{request_id} cancelled."

    def _customer_reschedule(self, customer_mobile: str, request_id: int, preferred_date: str, preferred_time: str) -> str:
        request = self.appointments.get_request(request_id)
        if not request or str(request.get("customer_mobile")) != str(customer_mobile):
            return "ఈ appointment మీది కాదు లేదా దొరకలేదు."
        assignment = self.appointments.get_assignment(request_id)
        if not assignment:
            return "Provider accept అయిన తర్వాత reschedule చేయండి."
        if not self.appointments.request_reschedule(
            request_id,
            customer_mobile,
            preferred_date,
            preferred_time,
        ):
            return "ఈ appointment ఇప్పుడు reschedule చేయలేరు."
        provider_mobile = str(assignment["provider_mobile"])
        self.whatsapp.send_text_message(
            provider_mobile,
            "🔄 Appointment reschedule request\n"
            f"Request: #{request_id}\n"
            f"Old: {request['preferred_date']} • {request['preferred_time']}\n"
            f"New: {preferred_date} • {preferred_time}\n\n"
            f"Accept: APPT RESCHEDULE ACCEPT {request_id}\n"
            f"Keep old schedule: APPT RESCHEDULE DECLINE {request_id}",
        )
        return (
            f"🔄 Appointment #{request_id} reschedule request providerకి పంపాను.\n"
            f"New: {preferred_date} • {preferred_time}\n"
            "Provider response వచ్చిన తర్వాత final status చెప్తాను."
        )

    def _provider_reschedule_action(self, provider_mobile: str, action: str, request_id: int) -> str:
        request = self.appointments.get_request(request_id)
        assignment = self.appointments.get_assignment(request_id)
        if not request or not assignment or str(assignment.get("provider_mobile")) != str(provider_mobile):
            return "ఈ appointment మీకు assigned కాలేదు."
        customer_mobile = self._customer_mobile(request)
        if action == "ACCEPT":
            if not self.appointments.provider_accept_reschedule(request_id, provider_mobile):
                return "ఈ reschedule request ఇప్పుడు accept చేయలేరు."
            refreshed = self.appointments.get_request(request_id) or request
            self.whatsapp.send_text_message(
                customer_mobile,
                "✅ Reschedule confirmed.\n"
                f"Appointment #{request_id}\n"
                f"Date: {refreshed['preferred_date']}\nTime: {refreshed['preferred_time']}\n"
                f"Provider contact: {self._contact(provider_mobile)}",
            )
            return f"✅ Appointment #{request_id} new schedule confirmed."
        previous_date = assignment.get("previous_date") or request.get("preferred_date")
        previous_time = assignment.get("previous_time") or request.get("preferred_time")
        if not self.appointments.provider_decline_reschedule(request_id, provider_mobile):
            return "ఈ reschedule request ఇప్పుడు decline చేయలేరు."
        self.whatsapp.send_text_message(
            customer_mobile,
            "ℹ️ Provider కొత్త time accept చేయలేకపోయారు. Old appointment schedule activeగా ఉంచాం.\n"
            f"Appointment #{request_id}: {previous_date} • {previous_time}",
        )
        return f"Appointment #{request_id} old schedule activeగా ఉంచాం."

    def _status(self, sender_mobile: str, request_id: int | None) -> str:
        request = self.appointments.get_request(request_id) if request_id is not None else None
        if request is None:
            request = self.appointments.latest_customer_request(sender_mobile)
        assignment = None
        if request is None:
            provider_assignment = self.appointments.latest_provider_assignment(sender_mobile)
            if provider_assignment:
                request = self.appointments.get_request(int(provider_assignment["request_id"]))
                assignment = provider_assignment
        if request is None:
            return "Active appointment దొరకలేదు."
        assignment = assignment or self.appointments.get_assignment(int(request["id"]))
        is_customer = str(request.get("customer_mobile")) == str(sender_mobile)
        is_provider = bool(assignment and str(assignment.get("provider_mobile")) == str(sender_mobile))
        if not is_customer and not is_provider:
            return "ఈ appointment status చూడడానికి permission లేదు."
        provider_name = self._provider_name(str(assignment["provider_mobile"])) if assignment else "Waiting for provider"
        return (
            f"📅 Appointment #{request['id']}\n"
            f"Status: {request['status']}\n"
            f"Type: {request['category']}\n"
            f"Provider: {provider_name}\n"
            f"Date: {request['preferred_date']}\n"
            f"Time: {request['preferred_time']}\n"
            f"Place: {request['area']}"
        )

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

    def _contact(self, mobile: str) -> str:
        if self.users is None:
            return str(mobile)
        user = self.users.find_by_whatsapp_mobile(str(mobile)) or {}
        return str(user.get("entered_mobile") or user.get("whatsapp_mobile") or mobile)

    @staticmethod
    def _extract_schedule(text: str) -> tuple[str | None, str | None]:
        lowered = str(text or "").casefold()
        preferred_date = None
        if "tomorrow" in lowered or "రేపు" in lowered:
            preferred_date = "Tomorrow"
        elif "today" in lowered or "ఈరోజు" in lowered or "ఇవాళ" in lowered:
            preferred_date = "Today"
        else:
            date_match = re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", text)
            if date_match:
                preferred_date = date_match.group(0)
        time_match = re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", text, flags=re.IGNORECASE)
        preferred_time = time_match.group(0).upper() if time_match else None
        if preferred_time is None:
            for marker, label in (
                ("morning", "Morning"), ("ఉదయం", "Morning"),
                ("afternoon", "Afternoon"), ("మధ్యాహ్నం", "Afternoon"),
                ("evening", "Evening"), ("సాయంత్రం", "Evening"),
                ("night", "Night"), ("రాత్రి", "Night"),
            ):
                if marker in lowered:
                    preferred_time = label
                    break
        return preferred_date, preferred_time

    @staticmethod
    def _area_matches(request_area: Any, provider_area: Any) -> bool:
        request_text = " ".join(str(request_area or "").casefold().strip().split())
        provider_text = " ".join(str(provider_area or "").casefold().strip().split())
        if request_text in {"", "nearby", "near me"}:
            return True
        if not provider_text:
            return True
        return request_text in provider_text or provider_text in request_text
