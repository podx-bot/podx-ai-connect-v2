import re

from app.models.session import ConversationStep
from app.repositories.user_repository import UserRepository
from app.services.session_registry import SessionRegistry


class ConversationService:
    CATEGORY_MAP = {
        "1": "Delivery",
        "delivery": "Delivery",
        "డెలివరీ": "Delivery",
        "2": "Catering",
        "catering": "Catering",
        "కేటరింగ్": "Catering",
        "3": "Warehouse",
        "warehouse": "Warehouse",
        "వేర్ హౌస్": "Warehouse",
        "4": "Hotel",
        "hotel": "Hotel",
        "హోటల్": "Hotel",
        "5": "House Cleaning",
        "house cleaning": "House Cleaning",
        "cleaning": "House Cleaning",
        "క్లీనింగ్": "House Cleaning",
        "6": "Driver",
        "driver": "Driver",
        "డ్రైవర్": "Driver",
        "7": "AC Technician",
        "ac technician": "AC Technician",
        "ac": "AC Technician",
        "8": "Electrician",
        "electrician": "Electrician",
        "ఎలక్ట్రిషియన్": "Electrician",
        "9": "Other",
        "other": "Other",
        "ఇతర": "Other"
    }

    EXPERIENCE_MAP = {
        "1": "Fresher",
        "fresher": "Fresher",
        "ఫ్రెషర్": "Fresher",
        "2": "1-2 Years",
        "1-2 years": "1-2 Years",
        "1 to 2 years": "1-2 Years",
        "3": "3-5 Years",
        "3-5 years": "3-5 Years",
        "3 to 5 years": "3-5 Years",
        "4": "5+ Years",
        "5+ years": "5+ Years",
        "5 years": "5+ Years"
    }

    AVAILABILITY_MAP = {
        "1": "Today",
        "today": "Today",
        "ఈరోజు": "Today",
        "2": "Tomorrow",
        "tomorrow": "Tomorrow",
        "రేపు": "Tomorrow",
        "3": "This Week",
        "this week": "This Week",
        "ఈ వారం": "This Week"
    }

    def __init__(
        self,
        user_repository: UserRepository,
        session_registry: SessionRegistry
    ) -> None:
        self.user_repository = user_repository
        self.session_registry = session_registry

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message).strip()
        normalized = clean_message.lower()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(
            sender_mobile
        )

        if normalized in {"reset", "restart", "start over"}:
            self.session_registry.reset(sender_mobile)
            return "Conversation reset అయింది. మళ్లీ Hi పంపండి."

        if (
            existing_user
            and existing_user.get("registration_complete") == 1
            and session.step == ConversationStep.START
        ):
            session.step = ConversationStep.MAIN_MENU

        if session.step == ConversationStep.START:
            session.step = ConversationStep.WAITING_MOBILE
            return (
                "🙏 PODX AI CONNECT కి స్వాగతం!\n\n"
                "దయచేసి మీ 10 అంకెల మొబైల్ నంబర్ పంపండి.\n"
                "ఉదాహరణ: 9876543210"
            )

        if session.step == ConversationStep.WAITING_MOBILE:
            mobile = self._extract_mobile(clean_message)
            if mobile is None:
                return "❌ సరైన 10 అంకెల మొబైల్ నంబర్ పంపండి."
            session.data["entered_mobile"] = mobile
            session.step = ConversationStep.WAITING_NAME
            return "మీ పేరు చెప్పండి."

        if session.step == ConversationStep.WAITING_NAME:
            if len(clean_message) < 2:
                return "దయచేసి మీ పూర్తి పేరు చెప్పండి."
            session.data["name"] = clean_message
            session.step = ConversationStep.WAITING_LANGUAGE
            return "మీకు ఏ భాషలో సేవ కావాలి?\n\n1. తెలుగు\n2. English\n3. हिंदी"

        if session.step == ConversationStep.WAITING_LANGUAGE:
            language_map = {
                "1": "Telugu", "తెలుగు": "Telugu", "telugu": "Telugu",
                "2": "English", "english": "English",
                "3": "Hindi", "हिंदी": "Hindi", "hindi": "Hindi"
            }
            language = language_map.get(normalized)
            if language is None:
                return "దయచేసి 1, 2 లేదా 3లో ఒకటి పంపండి."
            session.data["language"] = language
            session.step = ConversationStep.WAITING_AREA
            return "మీ ప్రాంతం లేదా పట్టణం పేరు చెప్పండి."

        if session.step == ConversationStep.WAITING_AREA:
            if len(clean_message) < 2:
                return "దయచేసి సరైన ప్రాంతం పేరు చెప్పండి."
            session.data["area"] = clean_message
            self.user_repository.create_or_update_registration(
                whatsapp_mobile=sender_mobile,
                entered_mobile=session.data["entered_mobile"],
                name=session.data["name"],
                language=session.data["language"],
                area=session.data["area"]
            )
            session.step = ConversationStep.MAIN_MENU
            return "✅ మీ Registration పూర్తైంది.\n\n" + self._main_menu()

        if session.step == ConversationStep.MAIN_MENU:
            if normalized in {"hi", "hello", "menu", "హాయ్"}:
                return self._main_menu()

            if self._is_job_seeker_intent(normalized):
                session.data.clear()
                session.data["role"] = "WORKER"
                session.step = ConversationStep.WORKER_CATEGORY
                return self._category_menu()

            if normalized in {"2", "వర్కర్స్ కావాలి", "workers కావాలి", "employer"}:
                return (
                    "👷 Employer workflow త్వరలో ప్రారంభమవుతుంది.\n\n"
                    + self._main_menu()
                )

            if normalized in {"3", "నా ప్రొఫైల్"}:
                user = self.user_repository.find_by_whatsapp_mobile(
                    sender_mobile
                )
                if not user:
                    return "Profile దొరకలేదు."
                return (
                    "👤 మీ ప్రొఫైల్\n\n"
                    f"పేరు: {user.get('name')}\n"
                    f"మొబైల్: {user.get('entered_mobile')}\n"
                    f"ప్రాంతం: {user.get('area')}\n"
                    f"పని: {user.get('job_category') or '-'}\n"
                    f"Experience: {user.get('experience') or '-'}\n"
                    f"Availability: {user.get('availability') or '-'}\n\n"
                    + self._main_menu()
                )

            if normalized in {"4", "సహాయం"}:
                return "PODX ఉద్యోగాలు మరియు వర్కర్స్‌ను కనెక్ట్ చేస్తుంది.\n\n" + self._main_menu()

            return "దయచేసి Menuలో ఉన్న option ఎంచుకోండి.\n\n" + self._main_menu()

        if session.step == ConversationStep.WORKER_CATEGORY:
            category = self.CATEGORY_MAP.get(normalized)
            if category is None:
                return "సరైన పని రకం ఎంచుకోండి.\n\n" + self._category_menu()
            session.data["category"] = category
            session.step = ConversationStep.WORKER_EXPERIENCE
            return (
                f"✅ {category} ఎంపిక చేశారు.\n\n"
                "మీ Experience ఎంత?\n"
                "1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years"
            )

        if session.step == ConversationStep.WORKER_EXPERIENCE:
            experience = self.EXPERIENCE_MAP.get(normalized)
            if experience is None:
                return "1, 2, 3 లేదా 4లో ఒకటి ఎంచుకోండి."
            session.data["experience"] = experience
            session.step = ConversationStep.WORKER_AVAILABILITY
            return (
                "మీ Availability ఎప్పుడు?\n"
                "1. Today\n2. Tomorrow\n3. This Week"
            )

        if session.step == ConversationStep.WORKER_AVAILABILITY:
            availability = self.AVAILABILITY_MAP.get(normalized)
            if availability is None:
                return "1, 2 లేదా 3లో ఒకటి ఎంచుకోండి."
            session.data["availability"] = availability
            self.user_repository.save_worker_profile(
                whatsapp_mobile=sender_mobile,
                category=session.data["category"],
                experience=session.data["experience"],
                availability=availability
            )
            session.step = ConversationStep.WORKER_LOCATION
            return (
                "📍 చివరి స్టెప్: WhatsApp Attachment ద్వారా "
                "మీ Current Location share చేయండి."
            )

        if session.step == ConversationStep.WORKER_LOCATION:
            return "📍 దయచేసి text కాకుండా WhatsApp Location share చేయండి."

        self.session_registry.reset(sender_mobile)
        return "Conversation reset అయింది. మళ్లీ Hi పంపండి."

    @staticmethod
    def _is_job_seeker_intent(message: str) -> bool:
        exact = {
            "1", "ఉద్యోగం కావాలి", "job కావాలి", "పని కావాలి",
            "job", "work", "worker", "job seeker"
        }
        return message in exact or "job కావాలి" in message or "పని కావాలి" in message

    @staticmethod
    def _extract_mobile(message: str):
        digits = re.sub(r"\D", "", message)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) != 10 or digits[0] not in {"6", "7", "8", "9"}:
            return None
        return digits

    @staticmethod
    def _category_menu() -> str:
        return (
            "💼 మీరు ఏ పని కోసం చూస్తున్నారు?\n\n"
            "1. Delivery\n2. Catering\n3. Warehouse\n4. Hotel\n"
            "5. House Cleaning\n6. Driver\n7. AC Technician\n"
            "8. Electrician\n9. Other"
        )

    @staticmethod
    def _main_menu() -> str:
        return (
            "మీకు ఏ సేవ కావాలి?\n\n"
            "1. ఉద్యోగం కావాలి\n"
            "2. వర్కర్స్ కావాలి\n"
            "3. నా ప్రొఫైల్\n"
            "4. సహాయం"
        )
