"""Free-form multilingual onboarding adapter.

Replaces the old fixed Telugu/English/Hindi language menu during registration.
Users may reply with any supported Indian language name/script; the preference is
stored in the current onboarding session and normal registration then continues.
"""
from __future__ import annotations

from app.models.session import ConversationStep


class MultilingualOnboardingService:
    LANGUAGE_MAP = {
        "1": "Telugu", "telugu": "Telugu", "తెలుగు": "Telugu",
        "2": "English", "english": "English",
        "3": "Hindi", "hindi": "Hindi", "हिंदी": "Hindi",
        "tamil": "Tamil", "தமிழ்": "Tamil",
        "kannada": "Kannada", "ಕನ್ನಡ": "Kannada",
        "malayalam": "Malayalam", "മലയാളം": "Malayalam",
        "marathi": "Marathi", "मराठी": "Marathi",
        "bengali": "Bengali", "bangla": "Bengali", "বাংলা": "Bengali",
        "gujarati": "Gujarati", "ગુજરાતી": "Gujarati",
        "punjabi": "Punjabi", "ਪੰਜਾਬੀ": "Punjabi",
        "odia": "Odia", "oriya": "Odia", "ଓଡ଼ିଆ": "Odia",
        "urdu": "Urdu", "اردو": "Urdu",
        "assamese": "Assamese", "অসমীয়া": "Assamese",
    }

    PROMPT = (
        "మీకు ఏ భాషలో మాట్లాడటం సౌకర్యంగా ఉంటుంది? అదే భాష పేరు లేదా ఆ భాషలో reply చేయండి. "
        "PODX అనేక Indian languages support చేస్తుంది."
    )

    def __init__(self, delegate, session_registry) -> None:
        self.delegate = delegate
        self.sessions = session_registry

    def process(self, sender_mobile: str, message: str) -> str:
        sender = str(sender_mobile)
        clean = str(message or "").strip()
        session = self.sessions.get(sender)

        if session.step == ConversationStep.WAITING_LANGUAGE:
            language = self._normalize_language(clean)
            if language is None:
                return "దయచేసి మీకు కావాల్సిన భాష పేరు పంపండి. ఉదా: తెలుగు, Tamil, ಕನ್ನಡ, मराठी, English."
            session.data["language"] = language
            session.step = ConversationStep.WAITING_AREA
            self.sessions.save(sender)
            return "సరే 👍 మీ ప్రాంతం లేదా పట్టణం పేరు చెప్పండి."

        before = session.step
        reply = self.delegate.process(sender_mobile=sender, message=clean)
        after = self.sessions.get(sender).step
        if before == ConversationStep.WAITING_NAME and after == ConversationStep.WAITING_LANGUAGE:
            return self.PROMPT
        return reply

    def _normalize_language(self, text: str):
        normalized = " ".join(str(text or "").strip().casefold().split())
        if not normalized:
            return None
        if normalized in self.LANGUAGE_MAP:
            return self.LANGUAGE_MAP[normalized]
        # Accept a short free-form language name rather than forcing a fixed menu.
        # Runtime translation/voice capabilities remain responsible for actual support.
        if len(normalized) <= 40 and not any(ch.isdigit() for ch in normalized):
            return str(text).strip().title()
        return None
