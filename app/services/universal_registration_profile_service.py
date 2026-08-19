"""Universal Registration/Profile V2.

Registration is deliberately minimal and language-first. PODX uses the incoming
WhatsApp sender number as the account contact for now; OTP and typed-number
verification are outside this flow. Business capabilities are attached later by
intent/domain flows, not selected up-front during registration.
"""
from __future__ import annotations

from app.models.session import ConversationStep


class UniversalRegistrationProfileService:
    LANGUAGE_MAP = {
        "1": "Telugu", "తెలుగు": "Telugu", "telugu": "Telugu",
        "2": "English", "english": "English",
        "3": "Hindi", "हिंदी": "Hindi", "hindi": "Hindi",
    }

    def __init__(self, user_repository, session_registry) -> None:
        self.user_repository = user_repository
        self.session_registry = session_registry

    def process(self, sender_mobile: str, message: str) -> str:
        clean = str(message or "").strip()
        normalized = clean.lower()
        session = self.session_registry.get(sender_mobile)
        data = getattr(session, "data", None)
        if not isinstance(data, dict):
            data = {}
            session.data = data
        step_name = str(getattr(session.step, "name", session.step))

        if step_name in {"WAITING_MOBILE", "WAITING_CAPABILITIES"}:
            user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
            if user and int(user.get("registration_complete") or 0) == 1:
                session.step = ConversationStep.MAIN_MENU
                return self._reply(sender_mobile, self._open_prompt(user.get("language")))
            data.clear()
            data["entered_mobile"] = sender_mobile
            session.step = ConversationStep.WAITING_LANGUAGE
            return self._reply(sender_mobile, self._language_prompt())

        if step_name == "START":
            data.clear()
            data["entered_mobile"] = sender_mobile
            session.step = ConversationStep.WAITING_LANGUAGE
            return self._reply(sender_mobile, self._language_prompt())

        if step_name == "WAITING_LANGUAGE":
            language = self.LANGUAGE_MAP.get(normalized)
            if language is None:
                return self._reply(sender_mobile, self._language_retry())
            data["language"] = language
            data["entered_mobile"] = sender_mobile
            session.step = ConversationStep.WAITING_NAME
            return self._reply(sender_mobile, self._name_prompt(language))

        if step_name == "WAITING_NAME":
            language = data.get("language") or "Telugu"
            if len(clean) < 2:
                return self._reply(sender_mobile, self._name_retry(language))
            data["name"] = clean
            session.step = ConversationStep.WAITING_AREA
            return self._reply(sender_mobile, self._area_prompt(language))

        if step_name == "WAITING_AREA":
            language = data.get("language") or "Telugu"
            if len(clean) < 2:
                return self._reply(sender_mobile, self._area_retry(language))
            data["area"] = clean
            self.user_repository.create_or_update_registration(
                whatsapp_mobile=sender_mobile,
                entered_mobile=sender_mobile,
                name=data["name"],
                language=language,
                area=clean,
            )
            session.step = ConversationStep.MAIN_MENU
            data.pop("face_welcome_handoff_pending", None)
            data.pop("face_welcome_photo_pending", None)
            return self._reply(sender_mobile, self._complete_prompt(language))

        data.clear()
        data["entered_mobile"] = sender_mobile
        session.step = ConversationStep.WAITING_LANGUAGE
        return self._reply(sender_mobile, self._language_prompt())

    def _reply(self, sender_mobile: str, text: str) -> str:
        save = getattr(self.session_registry, "save", None)
        if callable(save):
            save(sender_mobile)
        return text

    @staticmethod
    def _language_prompt() -> str:
        return (
            "🙏 PODX AI CONNECT కి స్వాగతం!\n\n"
            "మీ భాషను ఎంచుకోండి / Choose your language / अपनी भाषा चुनें\n\n"
            "1. తెలుగు\n2. English\n3. हिंदी"
        )

    @staticmethod
    def _language_retry() -> str:
        return "దయచేసి 1, 2 లేదా 3 ఎంచుకోండి. / Please choose 1, 2 or 3. / कृपया 1, 2 या 3 चुनें।"

    @staticmethod
    def _name_prompt(language: str) -> str:
        if language == "English": return "What is your name?"
        if language == "Hindi": return "आपका नाम क्या है?"
        return "మీ పేరు చెప్పండి."

    @staticmethod
    def _name_retry(language: str) -> str:
        if language == "English": return "Please tell me your name."
        if language == "Hindi": return "कृपया अपना नाम बताएं।"
        return "దయచేసి మీ పేరు చెప్పండి."

    @staticmethod
    def _area_prompt(language: str) -> str:
        if language == "English": return "Tell me your area or town."
        if language == "Hindi": return "अपना क्षेत्र या शहर बताएं।"
        return "మీ ప్రాంతం లేదా పట్టణం పేరు చెప్పండి."

    @staticmethod
    def _area_retry(language: str) -> str:
        if language == "English": return "Please enter a valid area or town name."
        if language == "Hindi": return "कृपया सही क्षेत्र या शहर का नाम बताएं।"
        return "దయచేసి సరైన ప్రాంతం లేదా పట్టణం పేరు చెప్పండి."

    @staticmethod
    def _complete_prompt(language: str) -> str:
        if language == "English": return "✅ Your PODX profile is ready. Tell me what you want to do."
        if language == "Hindi": return "✅ आपका PODX प्रोफ़ाइल तैयार है। अब बताएं आपको क्या चाहिए।"
        return "✅ మీ PODX ప్రొఫైల్ సిద్ధమైంది. ఇప్పుడు మీకు ఏం కావాలో చెప్పండి."

    @staticmethod
    def _open_prompt(language: str | None) -> str:
        return UniversalRegistrationProfileService._complete_prompt(language or "Telugu")
