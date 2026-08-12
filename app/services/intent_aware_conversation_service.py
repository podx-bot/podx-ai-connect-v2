from app.models.session import ConversationStep
from app.services.conversation_service import ConversationService
from app.services.intent_router_service import IntentRouterService


class IntentAwareConversationService(ConversationService):
    """Add invisible free-form routing without disturbing active workflows."""

    ROUTED_COMMANDS = {
        "JOB_SEEKER": "1",
        "EMPLOYER": "2",
        "PROFILE": "3",
        "HELP": "4",
    }

    def __init__(self, user_repository, session_registry, intent_router: IntentRouterService) -> None:
        super().__init__(
            user_repository=user_repository,
            session_registry=session_registry,
        )
        self.intent_router = intent_router

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(
            existing_user and existing_user.get("registration_complete") == 1
        )

        # Never let intent classification interrupt registration or an active
        # multi-step job workflow. It is used only at the conversational home.
        router_allowed = registered and session.step in {
            ConversationStep.START,
            ConversationStep.MAIN_MENU,
        }

        if router_allowed:
            classification = self.intent_router.classify(clean_message)
            intent = classification.get("intent", "UNKNOWN")
            routed_command = self.ROUTED_COMMANDS.get(intent)
            if routed_command:
                return super().process(sender_mobile, routed_command)

            # These product intents are recognized now so future modules can plug
            # into the same router without changing the WhatsApp entry point.
            if intent == "APPOINTMENT":
                return self._reply(
                    sender_mobile,
                    "📅 మీకు Appointment/Booking కావాలని అర్థమైంది. "
                    "Appointments module త్వరలో ఇదే PODXలో direct bookingకి connect అవుతుంది.",
                )
            if intent == "SERVICE":
                return self._reply(
                    sender_mobile,
                    "🛠️ మీకు local service కావాలని అర్థమైంది. "
                    "Services module త్వరలో nearby providersకి directగా connect చేస్తుంది.",
                )
            if intent == "SHOP_PRODUCT":
                return self._reply(
                    sender_mobile,
                    "🛍️ మీరు shop/product గురించి అడుగుతున్నారని అర్థమైంది. "
                    "Shops & Products module త్వరలో local availability, price, contact చూపిస్తుంది.",
                )

        return super().process(sender_mobile, clean_message)
