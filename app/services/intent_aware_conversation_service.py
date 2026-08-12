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

    APPOINTMENT_STEPS = {
        ConversationStep.APPOINTMENT_CATEGORY,
        ConversationStep.APPOINTMENT_AREA,
        ConversationStep.APPOINTMENT_DATE,
        ConversationStep.APPOINTMENT_TIME,
    }

    INTENT_SWITCH_STEPS = {
        ConversationStep.START,
        ConversationStep.MAIN_MENU,
        ConversationStep.WORKER_CATEGORY,
        ConversationStep.EMPLOYER_SERVICE,
    }

    def __init__(
        self,
        user_repository,
        session_registry,
        intent_router: IntentRouterService,
        appointment_service=None,
    ) -> None:
        super().__init__(
            user_repository=user_repository,
            session_registry=session_registry,
        )
        self.intent_router = intent_router
        self.appointment_service = appointment_service

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(
            existing_user and existing_user.get("registration_complete") == 1
        )

        if self.appointment_service and session.step in self.APPOINTMENT_STEPS:
            appointment_reply = self.appointment_service.process(
                sender_mobile,
                clean_message,
            )
            if appointment_reply is not None:
                return appointment_reply

        router_allowed = registered and session.step in self.INTENT_SWITCH_STEPS

        if router_allowed:
            classification = self.intent_router.classify(clean_message)
            intent = classification.get("intent", "UNKNOWN")

            if intent == "APPOINTMENT" and self.appointment_service:
                return self.appointment_service.start(
                    sender_mobile,
                    initial_message=clean_message,
                )

            if session.step in {ConversationStep.START, ConversationStep.MAIN_MENU}:
                routed_command = self.ROUTED_COMMANDS.get(intent)
                if routed_command:
                    return super().process(sender_mobile, routed_command)

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
