from app.models.session import ConversationStep


class AppointmentService:
    CATEGORY_ALIASES = {
        "1": "Doctor",
        "doctor": "Doctor",
        "డాక్టర్": "Doctor",
        "2": "Hospital/Clinic",
        "hospital": "Hospital/Clinic",
        "clinic": "Hospital/Clinic",
        "హాస్పిటల్": "Hospital/Clinic",
        "క్లినిక్": "Hospital/Clinic",
        "3": "Salon",
        "salon": "Salon",
        "సెలూన్": "Salon",
        "4": "Beauty Parlour",
        "beauty parlour": "Beauty Parlour",
        "parlour": "Beauty Parlour",
        "బ్యూటీ పార్లర్": "Beauty Parlour",
        "5": "Other",
        "other": "Other",
        "ఇతర": "Other",
    }

    def __init__(self, repository, session_registry) -> None:
        self.repository = repository
        self.session_registry = session_registry

    def start(self, sender_mobile: str) -> str:
        session = self.session_registry.get(sender_mobile)
        session.data.clear()
        session.step = ConversationStep.APPOINTMENT_CATEGORY
        self.session_registry.save(sender_mobile)
        return (
            "📅 Appointment booking ప్రారంభిద్దాం.\n\n"
            "ఏది కావాలి?\n"
            "1. Doctor\n2. Hospital/Clinic\n3. Salon\n4. Beauty Parlour\n5. Other"
        )

    def process(self, sender_mobile: str, message: str) -> str | None:
        session = self.session_registry.get(sender_mobile)
        text = " ".join(str(message or "").strip().split())
        normalized = text.lower()

        if session.step == ConversationStep.APPOINTMENT_CATEGORY:
            category = self.CATEGORY_ALIASES.get(normalized)
            if category is None:
                return (
                    "దయచేసి appointment type చెప్పండి: Doctor, Hospital/Clinic, "
                    "Salon, Beauty Parlour లేదా Other."
                )
            session.data["appointment_category"] = category
            session.step = ConversationStep.APPOINTMENT_AREA
            self.session_registry.save(sender_mobile)
            return f"✅ {category}. ఇప్పుడు మీ area / locality పేరు చెప్పండి."

        if session.step == ConversationStep.APPOINTMENT_AREA:
            if len(text) < 2:
                return "దయచేసి మీ area లేదా locality పేరు చెప్పండి."
            session.data["appointment_area"] = text
            session.step = ConversationStep.APPOINTMENT_DATE
            self.session_registry.save(sender_mobile)
            return "ఏ రోజు appointment కావాలి? ఉదాహరణ: Today, Tomorrow లేదా 15-08-2026."

        if session.step == ConversationStep.APPOINTMENT_DATE:
            if len(text) < 2:
                return "దయచేసి appointment date చెప్పండి."
            session.data["appointment_date"] = text
            session.step = ConversationStep.APPOINTMENT_TIME
            self.session_registry.save(sender_mobile)
            return "ఏ సమయం కావాలి? ఉదాహరణ: 10 AM, 4:30 PM లేదా Evening."

        if session.step == ConversationStep.APPOINTMENT_TIME:
            if len(text) < 2:
                return "దయచేసి preferred time చెప్పండి."
            request = self.repository.create_request(
                customer_mobile=sender_mobile,
                category=session.data.get("appointment_category", "Other"),
                area=session.data.get("appointment_area", ""),
                preferred_date=session.data.get("appointment_date", ""),
                preferred_time=text,
            )
            session.step = ConversationStep.MAIN_MENU
            session.data.clear()
            self.session_registry.save(sender_mobile)
            return (
                "✅ Appointment request save అయింది.\n\n"
                f"Request ID: #{request['id']}\n"
                f"Type: {request['category']}\n"
                f"Area: {request['area']}\n"
                f"Date: {request['preferred_date']}\n"
                f"Time: {request['preferred_time']}\n\n"
                "Next versionలో nearby businesses + available slotsతో direct confirmation వస్తుంది."
            )

        return None
