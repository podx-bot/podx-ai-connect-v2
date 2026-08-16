import re

from app.models.session import ConversationStep


class AppointmentService:
    CATEGORY_ALIASES = {
        "1": "Doctor", "doctor": "Doctor", "డాక్టర్": "Doctor",
        "2": "Hospital/Clinic", "hospital": "Hospital/Clinic", "clinic": "Hospital/Clinic", "హాస్పిటల్": "Hospital/Clinic", "క్లినిక్": "Hospital/Clinic",
        "3": "Salon", "salon": "Salon", "సెలూన్": "Salon",
        "4": "Beauty Parlour", "beauty parlour": "Beauty Parlour", "parlour": "Beauty Parlour", "బ్యూటీ పార్లర్": "Beauty Parlour",
        "5": "Other", "other": "Other", "ఇతర": "Other",
    }

    def __init__(self, repository, session_registry, provider_runtime=None) -> None:
        self.repository = repository
        self.session_registry = session_registry
        self.provider_runtime = provider_runtime

    def set_provider_runtime(self, provider_runtime) -> None:
        self.provider_runtime = provider_runtime

    def process_provider_command(self, sender_mobile: str, message: str) -> str | None:
        if self.provider_runtime is None:
            return None
        return self.provider_runtime.process_provider_command(sender_mobile, message)

    def start(self, sender_mobile: str, initial_message: str = "") -> str:
        session = self.session_registry.get(sender_mobile)
        session.data.clear()

        category = self._category_from_free_text(initial_message)
        if category:
            session.data["appointment_category"] = category
            parsed_date, parsed_time = self._extract_schedule(initial_message)
            target = self._normalize_target(initial_message)
            if target and parsed_date and parsed_time:
                session.data["appointment_area"] = target
                return self._save_request(sender_mobile, session, parsed_date, parsed_time)
            session.step = ConversationStep.APPOINTMENT_AREA
            self.session_registry.save(sender_mobile)
            return self._target_prompt(category)

        session.step = ConversationStep.APPOINTMENT_CATEGORY
        self.session_registry.save(sender_mobile)
        return (
            "📅 Appointment booking ప్రారంభిద్దాం.\n\nఏది కావాలి?\n"
            "1. Doctor\n2. Hospital/Clinic\n3. Salon\n4. Beauty Parlour\n5. Other"
        )

    def process(self, sender_mobile: str, message: str) -> str | None:
        session = self.session_registry.get(sender_mobile)
        text = " ".join(str(message or "").strip().split())
        normalized = text.lower()

        if session.step == ConversationStep.APPOINTMENT_CATEGORY:
            category = self.CATEGORY_ALIASES.get(normalized) or self._category_from_free_text(text)
            if category is None:
                return "Appointment type చెప్పండి: Doctor, Hospital/Clinic, Salon, Beauty Parlour లేదా Other."
            session.data["appointment_category"] = category
            parsed_date, parsed_time = self._extract_schedule(text)
            target = self._normalize_target(text)
            if target and parsed_date and parsed_time:
                session.data["appointment_area"] = target
                return self._save_request(sender_mobile, session, parsed_date, parsed_time)
            session.step = ConversationStep.APPOINTMENT_AREA
            self.session_registry.save(sender_mobile)
            return self._target_prompt(category)

        if session.step == ConversationStep.APPOINTMENT_AREA:
            if len(text) < 2:
                return self._target_prompt(session.data.get("appointment_category", "Appointment"))
            session.data["appointment_area"] = self._normalize_target(text)
            parsed_date, parsed_time = self._extract_schedule(text)
            if parsed_date and parsed_time:
                return self._save_request(sender_mobile, session, parsed_date, parsed_time)
            session.step = ConversationStep.APPOINTMENT_DATE
            self.session_registry.save(sender_mobile)
            return "ఏ రోజు + ఏ సమయం కావాలో ఒకేసారి చెప్పండి. ఉదా: Tomorrow 4 PM."

        if session.step == ConversationStep.APPOINTMENT_DATE:
            if len(text) < 2:
                return "రోజు + సమయం ఒకేసారి చెప్పండి. ఉదా: Tomorrow 4 PM."
            parsed_date, parsed_time = self._extract_schedule(text)
            if parsed_date and parsed_time:
                return self._save_request(sender_mobile, session, parsed_date, parsed_time)
            session.data["appointment_date"] = parsed_date or text
            session.step = ConversationStep.APPOINTMENT_TIME
            self.session_registry.save(sender_mobile)
            return "సమయం మాత్రమే చెప్పండి. ఉదా: 10 AM లేదా 4:30 PM."

        if session.step == ConversationStep.APPOINTMENT_TIME:
            if len(text) < 2:
                return "Preferred time చెప్పండి."
            return self._save_request(sender_mobile, session, session.data.get("appointment_date", "Today"), text)
        return None

    def _save_request(self, sender_mobile: str, session, preferred_date: str, preferred_time: str) -> str:
        request = self.repository.create_request(
            customer_mobile=sender_mobile,
            category=session.data.get("appointment_category", "Other"),
            area=session.data.get("appointment_area", "Nearby"),
            preferred_date=preferred_date,
            preferred_time=preferred_time,
        )
        provider_result = None
        if self.provider_runtime is not None:
            try:
                provider_result = self.provider_runtime.notify_matching_providers(request)
            except Exception as error:
                print(f"PODX APPOINTMENT PROVIDER NOTIFY failed={type(error).__name__}: {error}", flush=True)
        session.step = ConversationStep.MAIN_MENU
        session.data.clear()
        self.session_registry.save(sender_mobile)
        provider_note = "\nMatching providersకి request పంపాను." if provider_result and int(provider_result.get("sent") or 0) > 0 else "\nRequest save అయింది. Matching provider available అయినప్పుడు PODX connect చేస్తుంది."
        return (
            "✅ Appointment request save అయింది.\n\n"
            f"Request ID: #{request['id']}\nType: {request['category']}\n"
            f"Place: {request['area']}\nDate: {request['preferred_date']}\nTime: {request['preferred_time']}"
            + provider_note
        )

    @classmethod
    def _category_from_free_text(cls, text: str) -> str | None:
        lowered = str(text or "").lower()
        for alias, category in cls.CATEGORY_ALIASES.items():
            if not alias.isdigit() and alias in lowered:
                return category
        return None

    @staticmethod
    def _target_prompt(category: str) -> str:
        return (
            f"✅ {category}. Nearby / area పేరు / specific {category} పేరు చెప్పండి. "
            "రోజు + సమయం కూడా అదే messageలో చెప్పండి. ఉదా: Vuyyuru, Tomorrow 4 PM."
        )

    @staticmethod
    def _normalize_target(text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ("nearby", "near me", "దగ్గరలో", "నా దగ్గర", "చుట్టుపక్కల")):
            return "Nearby"
        cleaned = re.sub(r"\b(?:today|tomorrow|ఈరోజు|రేపు|ఇవాళ)\b", " ", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", " ", cleaned)
        cleaned = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:appointment|booking|book|కావాలి|అపాయింట్మెంట్)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip(" ,.-")
        return cleaned or "Nearby"

    @staticmethod
    def _extract_schedule(text: str) -> tuple[str | None, str | None]:
        lowered = text.lower()
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
            for marker, label in (("morning", "Morning"), ("ఉదయం", "Morning"), ("afternoon", "Afternoon"), ("మధ్యాహ్నం", "Afternoon"), ("evening", "Evening"), ("సాయంత్రం", "Evening"), ("night", "Night"), ("రాత్రి", "Night")):
                if marker in lowered:
                    preferred_time = label
                    break
        return preferred_date, preferred_time
