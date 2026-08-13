import re

from app.models.session import ConversationStep
from app.repositories.user_repository import UserRepository
from app.services.session_registry import SessionRegistry


class ConversationService:
    CATEGORY_MAP = {
        "1": "Delivery", "delivery": "Delivery", "డెలివరీ": "Delivery",
        "2": "Catering", "catering": "Catering", "కేటరింగ్": "Catering",
        "3": "Warehouse", "warehouse": "Warehouse", "వేర్ హౌస్": "Warehouse",
        "4": "Hotel", "hotel": "Hotel", "హోటల్": "Hotel",
        "5": "House Cleaning", "house cleaning": "House Cleaning", "cleaning": "House Cleaning", "క్లీనింగ్": "House Cleaning",
        "6": "Driver", "driver": "Driver", "డ్రైవర్": "Driver",
        "7": "AC Technician", "ac technician": "AC Technician", "ac": "AC Technician",
        "8": "Electrician", "electrician": "Electrician", "ఎలక్ట్రిషియన్": "Electrician",
        "9": "Other", "other": "Other", "ఇతర": "Other"
    }
    EXPERIENCE_MAP = {
        "1": "Fresher", "fresher": "Fresher", "ఫ్రెషర్": "Fresher",
        "2": "1-2 Years", "1-2 years": "1-2 Years", "1 to 2 years": "1-2 Years",
        "3": "3-5 Years", "3-5 years": "3-5 Years", "3 to 5 years": "3-5 Years",
        "4": "5+ Years", "5+ years": "5+ Years", "5 years": "5+ Years"
    }
    AVAILABILITY_MAP = {
        "1": "Today", "today": "Today", "ఈరోజు": "Today",
        "2": "Tomorrow", "tomorrow": "Tomorrow", "రేపు": "Tomorrow",
        "3": "This Week", "this week": "This Week", "ఈ వారం": "This Week"
    }
    CAPABILITY_OPTIONS = {
        "1": "BUYER",
        "2": "SELLER",
        "3": "SERVICE_CUSTOMER",
        "4": "SERVICE_PROVIDER",
        "5": "WORKER",
        "6": "EMPLOYER",
    }
    CAPABILITY_LABELS = {
        "BUYER": "Buy products",
        "SELLER": "Sell products",
        "SERVICE_CUSTOMER": "Need services",
        "SERVICE_PROVIDER": "Provide services",
        "WORKER": "Find work",
        "EMPLOYER": "Hire workers",
    }

    def __init__(self, user_repository: UserRepository, session_registry: SessionRegistry) -> None:
        self.user_repository = user_repository
        self.session_registry = session_registry

    def _reply(self, sender_mobile: str, text: str) -> str:
        self.session_registry.save(sender_mobile)
        return text

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message).strip()
        normalized = clean_message.lower()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)

        if normalized in {"reset", "restart", "start over", "మళ్లీ మొదలు"}:
            self.session_registry.reset(sender_mobile)
            return "Conversation reset అయింది. మళ్లీ Hi పంపండి."

        if normalized in {"hi", "hello", "hey", "హాయ్", "హలో"}:
            if (
                existing_user
                and existing_user.get("registration_complete") == 1
                and session.step != ConversationStep.WAITING_CAPABILITIES
            ):
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                return self._reply(sender_mobile, self._main_menu())

        if normalized in {"help", "సహాయం"}:
            return self._reply(sender_mobile, "PODX సహాయం:\nMenu - ప్రధాన మెనూ\nBack - ఒక దశ వెనక్కి\nRestart - మళ్లీ మొదలు\n\n" + self._main_menu())

        if normalized in {"menu", "main menu", "మెను", "మెనూ"}:
            if existing_user and existing_user.get("registration_complete") == 1:
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                return self._reply(sender_mobile, self._main_menu())
            self.session_registry.reset(sender_mobile)
            return "ముందుగా Registration పూర్తి చేయాలి. Hi పంపండి."

        if normalized in {"back", "వెనక్కి"}:
            return self._go_back(sender_mobile, session, existing_user)

        if existing_user and existing_user.get("registration_complete") == 1 and session.step == ConversationStep.START:
            session.step = ConversationStep.MAIN_MENU

        if session.step == ConversationStep.START:
            session.step = ConversationStep.WAITING_MOBILE
            return self._reply(sender_mobile, "🙏 PODX AI CONNECT కి స్వాగతం!\n\nదయచేసి మీ 10 అంకెల మొబైల్ నంబర్ పంపండి.\nఉదాహరణ: 9876543210")

        if session.step == ConversationStep.WAITING_MOBILE:
            mobile = self._extract_mobile(clean_message)
            if mobile is None:
                return self._reply(sender_mobile, "❌ సరైన 10 అంకెల మొబైల్ నంబర్ పంపండి.")
            session.data["entered_mobile"] = mobile
            session.step = ConversationStep.WAITING_NAME
            return self._reply(sender_mobile, "మీ పేరు చెప్పండి.")

        if session.step == ConversationStep.WAITING_NAME:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "దయచేసి మీ పూర్తి పేరు చెప్పండి.")
            session.data["name"] = clean_message
            session.step = ConversationStep.WAITING_LANGUAGE
            return self._reply(sender_mobile, "మీకు ఏ భాషలో సేవ కావాలి?\n\n1. తెలుగు\n2. English\n3. हिंदी")

        if session.step == ConversationStep.WAITING_LANGUAGE:
            language_map = {"1": "Telugu", "తెలుగు": "Telugu", "telugu": "Telugu", "2": "English", "english": "English", "3": "Hindi", "हिंदी": "Hindi", "hindi": "Hindi"}
            language = language_map.get(normalized)
            if language is None:
                return self._reply(sender_mobile, "దయచేసి 1, 2 లేదా 3లో ఒకటి పంపండి.")
            session.data["language"] = language
            session.step = ConversationStep.WAITING_AREA
            return self._reply(sender_mobile, "మీ ప్రాంతం లేదా పట్టణం పేరు చెప్పండి.")

        if session.step == ConversationStep.WAITING_AREA:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "దయచేసి సరైన ప్రాంతం పేరు చెప్పండి.")
            session.data["area"] = clean_message
            self.user_repository.create_or_update_registration(
                whatsapp_mobile=sender_mobile,
                entered_mobile=session.data["entered_mobile"],
                name=session.data["name"],
                language=session.data["language"],
                area=session.data["area"],
            )
            session.step = ConversationStep.WAITING_CAPABILITIES
            return self._reply(sender_mobile, self._capability_menu())

        if session.step == ConversationStep.WAITING_CAPABILITIES:
            capabilities = self._parse_capabilities(clean_message)
            if not capabilities:
                return self._reply(
                    sender_mobile,
                    "ఒకటి లేదా ఎక్కువ options ఎంచుకోండి. ఉదాహరణ: 1,2 లేదా 5,6\n\n" + self._capability_menu(),
                )
            self.user_repository.add_capabilities(
                sender_mobile,
                capabilities,
                source="registration",
            )
            session.data["registration_capabilities"] = capabilities
            session.step = ConversationStep.MAIN_MENU
            selected = ", ".join(self.CAPABILITY_LABELS[item] for item in capabilities)
            return self._reply(
                sender_mobile,
                f"✅ మీ Registration పూర్తైంది.\nమీ PODX roles: {selected}\n\n" + self._main_menu(),
            )

        if session.step == ConversationStep.MAIN_MENU:
            if normalized in {"hi", "hello", "menu", "హాయ్"}:
                return self._reply(sender_mobile, self._main_menu())
            if self._is_job_seeker_intent(normalized):
                session.data.clear()
                session.data["role"] = "WORKER"
                session.step = ConversationStep.WORKER_CATEGORY
                return self._reply(sender_mobile, self._category_menu())
            if normalized in {"2", "వర్కర్స్ కావాలి", "workers కావాలి", "employer"}:
                session.data.clear()
                session.data["role"] = "EMPLOYER"
                session.step = ConversationStep.EMPLOYER_SERVICE
                return self._reply(sender_mobile, "👷 Employer workflow ప్రారంభమవుతుంది.\n\n" + self._employer_service_menu())
            if normalized in {"3", "నా ప్రొఫైల్"}:
                user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
                if not user:
                    return self._reply(sender_mobile, "Profile దొరకలేదు.")
                capabilities = user.get("capabilities") or []
                capability_text = ", ".join(self.CAPABILITY_LABELS.get(item, item) for item in capabilities) or "-"
                return self._reply(sender_mobile, "👤 మీ ప్రొఫైల్\n\n" f"పేరు: {user.get('name')}\n" f"మొబైల్: {user.get('entered_mobile')}\n" f"ప్రాంతం: {user.get('area')}\n" f"PODX roles: {capability_text}\n" f"పని: {user.get('job_category') or '-'}\n" f"Experience: {user.get('experience') or '-'}\n" f"Availability: {user.get('availability') or '-'}\n\n" + self._main_menu())
            if normalized in {"4", "సహాయం"}:
                return self._reply(sender_mobile, "PODX ఉద్యోగాలు, వర్కర్స్, products మరియు local servicesను connect చేయడానికి నిర్మించబడుతోంది.\n\n" + self._main_menu())
            return self._reply(sender_mobile, "దయచేసి Menuలో ఉన్న option ఎంచుకోండి.\n\n" + self._main_menu())

        if session.step == ConversationStep.EMPLOYER_SERVICE:
            service = self.CATEGORY_MAP.get(normalized)
            if service is None:
                return self._reply(sender_mobile, "దయచేసి సరైన సేవ ఎంచుకోండి.\n\n" + self._employer_service_menu())
            session.data["service"] = service
            session.step = ConversationStep.EMPLOYER_REQUIREMENT
            return self._reply(sender_mobile, f"✅ {service} ఎంపిక చేశారు.\n\nదయచేసి మీ job requirement వివరాలు పంపండి.")

        if session.step == ConversationStep.EMPLOYER_REQUIREMENT:
            if len(clean_message) < 5:
                return self._reply(sender_mobile, "దయచేసి job గురించి సరైన వివరాలు పంపండి (చిన్న వాక్యంగా కాదు).")
            requirement = clean_message
            session.data["requirement"] = requirement
            try:
                self.user_repository.save_employer_post(whatsapp_mobile=sender_mobile, service=session.data.get("service"), requirement=requirement)
            except Exception:
                pass
            session.step = ConversationStep.EMPLOYER_LOCATION
            return self._reply(sender_mobile, "📍 చివరి స్టెప్: WhatsApp Attachment ద్వారా మీ Job Location share చేయండి.")

        if session.step == ConversationStep.EMPLOYER_LOCATION:
            return self._reply(sender_mobile, "📍 దయచేసి text కాకుండా WhatsApp Location share చేయండి.")

        if session.step == ConversationStep.WORKER_CATEGORY:
            category = self.CATEGORY_MAP.get(normalized)
            if category is None:
                return self._reply(sender_mobile, "సరైన పని రకం ఎంచుకోండి.\n\n" + self._category_menu())
            session.data["category"] = category
            session.step = ConversationStep.WORKER_EXPERIENCE
            return self._reply(sender_mobile, f"✅ {category} ఎంపిక చేశారు.\n\nమీ Experience ఎంత?\n1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years")

        if session.step == ConversationStep.WORKER_EXPERIENCE:
            experience = self.EXPERIENCE_MAP.get(normalized)
            if experience is None:
                return self._reply(sender_mobile, "1, 2, 3 లేదా 4లో ఒకటి ఎంచుకోండి.")
            session.data["experience"] = experience
            session.step = ConversationStep.WORKER_AVAILABILITY
            return self._reply(sender_mobile, "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week")

        if session.step == ConversationStep.WORKER_AVAILABILITY:
            availability = self.AVAILABILITY_MAP.get(normalized)
            if availability is None:
                return self._reply(sender_mobile, "1, 2 లేదా 3లో ఒకటి ఎంచుకోండి.")
            session.data["availability"] = availability
            self.user_repository.save_worker_profile(whatsapp_mobile=sender_mobile, category=session.data["category"], experience=session.data["experience"], availability=availability)
            session.step = ConversationStep.WORKER_LOCATION
            return self._reply(sender_mobile, "📍 చివరి స్టెప్: WhatsApp Attachment ద్వారా మీ Current Location share చేయండి.")

        if session.step == ConversationStep.WORKER_LOCATION:
            return self._reply(sender_mobile, "📍 దయచేసి text కాకుండా WhatsApp Location share చేయండి.")

        self.session_registry.reset(sender_mobile)
        return "Conversation reset అయింది. మళ్లీ Hi పంపండి."

    def _go_back(self, sender_mobile, session, existing_user) -> str:
        previous = {
            ConversationStep.WAITING_NAME: ConversationStep.WAITING_MOBILE,
            ConversationStep.WAITING_LANGUAGE: ConversationStep.WAITING_NAME,
            ConversationStep.WAITING_AREA: ConversationStep.WAITING_LANGUAGE,
            ConversationStep.WAITING_CAPABILITIES: ConversationStep.WAITING_AREA,
            ConversationStep.WORKER_CATEGORY: ConversationStep.MAIN_MENU,
            ConversationStep.WORKER_EXPERIENCE: ConversationStep.WORKER_CATEGORY,
            ConversationStep.WORKER_AVAILABILITY: ConversationStep.WORKER_EXPERIENCE,
            ConversationStep.WORKER_LOCATION: ConversationStep.WORKER_AVAILABILITY,
            ConversationStep.EMPLOYER_SERVICE: ConversationStep.MAIN_MENU,
            ConversationStep.EMPLOYER_REQUIREMENT: ConversationStep.EMPLOYER_SERVICE,
            ConversationStep.EMPLOYER_LOCATION: ConversationStep.EMPLOYER_REQUIREMENT,
        }
        if session.step == ConversationStep.MAIN_MENU:
            return self._reply(sender_mobile, self._main_menu())
        target = previous.get(session.step)
        if target is None:
            if existing_user and existing_user.get("registration_complete") == 1:
                session.step = ConversationStep.MAIN_MENU
                return self._reply(sender_mobile, self._main_menu())
            self.session_registry.reset(sender_mobile)
            return "మళ్లీ మొదలు పెట్టాం. Hi పంపండి."
        session.step = target
        prompts = {
            ConversationStep.WAITING_MOBILE: "మీ 10 అంకెల మొబైల్ నంబర్ పంపండి.",
            ConversationStep.WAITING_NAME: "మీ పేరు చెప్పండి.",
            ConversationStep.WAITING_LANGUAGE: "మీ భాష ఎంచుకోండి:\n1. తెలుగు\n2. English\n3. हिंदी",
            ConversationStep.WAITING_AREA: "మీ ప్రాంతం లేదా పట్టణం పేరు చెప్పండి.",
            ConversationStep.WAITING_CAPABILITIES: self._capability_menu(),
            ConversationStep.MAIN_MENU: self._main_menu(),
            ConversationStep.WORKER_CATEGORY: self._category_menu(),
            ConversationStep.WORKER_EXPERIENCE: "మీ Experience ఎంత?\n1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years",
            ConversationStep.WORKER_AVAILABILITY: "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week",
            ConversationStep.EMPLOYER_SERVICE: self._employer_service_menu(),
            ConversationStep.EMPLOYER_REQUIREMENT: "దయచేసి మీ job requirement వివరాలు పంపండి.",
            ConversationStep.EMPLOYER_LOCATION: "📍 చివరి స్టెప్: WhatsApp Attachment ద్వారా మీ Job Location share చేయండి.",
        }
        return self._reply(sender_mobile, prompts.get(target, "Previous stepకి వచ్చారు."))

    @classmethod
    def _parse_capabilities(cls, message: str) -> list[str]:
        normalized = str(message or "").lower().strip()
        if normalized in {"7", "all", "అన్నీ", "all roles", "everything"}:
            return list(cls.CAPABILITY_OPTIONS.values())

        selected = []
        for number in re.findall(r"(?<!\d)[1-6](?!\d)", normalized):
            capability = cls.CAPABILITY_OPTIONS[number]
            if capability not in selected:
                selected.append(capability)

        keyword_map = {
            "BUYER": ("buyer", "buy", "కొనాలి", "కొనుగోలు", "కొంటాను"),
            "SELLER": ("seller", "sell", "అమ్మాలి", "అమ్ముతాను", "విక్రయం"),
            "SERVICE_CUSTOMER": ("need service", "service కావాలి", "సేవ కావాలి"),
            "SERVICE_PROVIDER": ("service provider", "provide service", "సేవ ఇస్తాను", "సర్వీస్ ఇస్తాను"),
            "WORKER": ("find job", "job seeker", "పని కావాలి", "ఉద్యోగం కావాలి"),
            "EMPLOYER": ("hire", "employer", "workers కావాలి", "వర్కర్స్ కావాలి"),
        }
        for capability, keywords in keyword_map.items():
            if any(keyword in normalized for keyword in keywords) and capability not in selected:
                selected.append(capability)
        return selected

    @staticmethod
    def _is_job_seeker_intent(message: str) -> bool:
        exact = {"1", "ఉద్యోగం కావాలి", "job కావాలి", "పని కావాలి", "job", "work", "worker", "job seeker"}
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
    def _capability_menu() -> str:
        return (
            "PODXలో మీరు ఏ విధంగా ఉపయోగించాలనుకుంటున్నారు?\n"
            "ఒకటి లేదా ఎక్కువ options ఎంచుకోవచ్చు. ఉదా: 1,2,5\n\n"
            "1. 🛒 Products కొనాలి (Buyer)\n"
            "2. 🏪 Products అమ్మాలి (Seller)\n"
            "3. 🔎 Service కావాలి\n"
            "4. 🛠️ Service ఇవ్వాలి\n"
            "5. 💼 పని కావాలి\n"
            "6. 👷 Workers కావాలి\n"
            "7. 🌐 అన్నీ / All\n\n"
            "తర్వాత కూడా మీ అవసరాన్ని బట్టి PODX కొత్త roleని automatically add చేయగలదు."
        )

    @staticmethod
    def _category_menu() -> str:
        return "💼 మీరు ఏ పని కోసం చూస్తున్నారు?\n\n1. Delivery\n2. Catering\n3. Warehouse\n4. Hotel\n5. House Cleaning\n6. Driver\n7. AC Technician\n8. Electrician\n9. Other"

    @staticmethod
    def _employer_service_menu() -> str:
        return "👷 మీరు ఏ సేవ కోసం వర్కర్స్ కోరుకుంటున్నారు?\n\n1. Delivery\n2. Catering\n3. Warehouse\n4. Hotel\n5. House Cleaning\n6. Driver\n7. AC Technician\n8. Electrician\n9. Other"

    @staticmethod
    def _main_menu() -> str:
        return "మీకు ఏ సేవ కావాలి?\n\n1. ఉద్యోగం కావాలి\n2. వర్కర్స్ కావాలి\n3. నా ప్రొఫైల్\n4. సహాయం"
