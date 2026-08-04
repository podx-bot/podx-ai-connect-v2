import re

from app.models.session import ConversationStep
from app.repositories.user_repository import UserRepository
from app.services.session_registry import SessionRegistry


class ConversationService:
    def __init__(
        self,
        user_repository: UserRepository,
        session_registry: SessionRegistry
    ) -> None:
        self.user_repository = user_repository
        self.session_registry = session_registry

    def process(
        self,
        sender_mobile: str,
        message: str
    ) -> str:
        clean_message = str(message).strip()
        session = self.session_registry.get(sender_mobile)

        existing_user = (
            self.user_repository.find_by_whatsapp_mobile(
                sender_mobile
            )
        )

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
                return (
                    "❌ దయచేసి సరైన 10 అంకెల మొబైల్ "
                    "నంబర్ పంపండి.\n"
                    "ఉదాహరణ: 9876543210"
                )

            session.data["entered_mobile"] = mobile
            session.step = ConversationStep.WAITING_NAME
            return "మీ పేరు చెప్పండి."

        if session.step == ConversationStep.WAITING_NAME:
            if len(clean_message) < 2:
                return "దయచేసి మీ పూర్తి పేరు చెప్పండి."

            session.data["name"] = clean_message
            session.step = ConversationStep.WAITING_LANGUAGE
            return (
                "మీకు ఏ భాషలో సేవ కావాలి?\n\n"
                "1. తెలుగు\n"
                "2. English\n"
                "3. हिंदी"
            )

        if session.step == ConversationStep.WAITING_LANGUAGE:
            language_map = {
                "1": "Telugu",
                "తెలుగు": "Telugu",
                "telugu": "Telugu",
                "2": "English",
                "english": "English",
                "3": "Hindi",
                "हिंदी": "Hindi",
                "hindi": "Hindi"
            }

            language = language_map.get(clean_message.lower())

            if language is None:
                return (
                    "దయచేసి 1, 2 లేదా 3లో ఒకటి పంపండి.\n\n"
                    "1. తెలుగు\n"
                    "2. English\n"
                    "3. हिंदी"
                )

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
            return (
                "✅ మీ Registration పూర్తైంది.\n\n"
                + self._main_menu()
            )

        if session.step == ConversationStep.MAIN_MENU:
            normalized = clean_message.lower()

            if normalized in {"hi", "hello", "menu", "హాయ్"}:
                return self._main_menu()

            if normalized in {"1", "ఉద్యోగం కావాలి"}:
                return (
                    "💼 Job Seeker workflow V2 Phase 2లో "
                    "ప్రారంభమవుతుంది.\n\n"
                    + self._main_menu()
                )

            if normalized in {"2", "వర్కర్స్ కావాలి"}:
                return (
                    "👷 Employer workflow V2 Phase 3లో "
                    "ప్రారంభమవుతుంది.\n\n"
                    + self._main_menu()
                )

            if normalized in {"3", "నా ప్రొఫైల్"}:
                user = (
                    self.user_repository.find_by_whatsapp_mobile(
                        sender_mobile
                    )
                )
                if not user:
                    return "Profile దొరకలేదు."

                return (
                    "👤 మీ ప్రొఫైల్\n\n"
                    f"పేరు: {user.get('name')}\n"
                    f"మొబైల్: {user.get('entered_mobile')}\n"
                    f"భాష: {user.get('language')}\n"
                    f"ప్రాంతం: {user.get('area')}\n\n"
                    + self._main_menu()
                )

            if normalized in {"4", "సహాయం"}:
                return (
                    "PODX మీకు ఉద్యోగాలు మరియు వర్కర్స్ "
                    "కనెక్ట్ చేయడంలో సహాయం చేస్తుంది.\n\n"
                    + self._main_menu()
                )

            return (
                "దయచేసి Menuలో ఉన్న option ఎంచుకోండి.\n\n"
                + self._main_menu()
            )

        self.session_registry.reset(sender_mobile)
        return (
            "Conversation reset అయింది. మళ్లీ Hi పంపండి."
        )

    @staticmethod
    def _extract_mobile(message: str):
        digits = re.sub(r"\D", "", message)

        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]

        if len(digits) != 10:
            return None

        if digits[0] not in {"6", "7", "8", "9"}:
            return None

        return digits

    @staticmethod
    def _main_menu() -> str:
        return (
            "మీకు ఏ సేవ కావాలి?\n\n"
            "1. ఉద్యోగం కావాలి\n"
            "2. వర్కర్స్ కావాలి\n"
            "3. నా ప్రొఫైల్\n"
            "4. సహాయం"
        )
