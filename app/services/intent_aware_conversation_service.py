from app.models.session import ConversationStep
from app.services.conversation_service import ConversationService
from app.services.intent_router_service import IntentRouterService
from app.services.smart_job_message_service import SmartJobMessageService


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

    APPOINTMENT_INTERRUPT_INTENTS = {
        "JOB_SEEKER",
        "EMPLOYER",
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
        self.smart_job_message_service = SmartJobMessageService()

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(
            existing_user and existing_user.get("registration_complete") == 1
        )

        if self.appointment_service and session.step in self.APPOINTMENT_STEPS:
            rule_classifier = getattr(self.intent_router, "_classify_rules", None)
            interrupt_intent = rule_classifier(clean_message) if callable(rule_classifier) else None
            if registered and interrupt_intent in self.APPOINTMENT_INTERRUPT_INTENTS:
                return self._route_smart_job(sender_mobile, clean_message, interrupt_intent)

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

            if intent in {"JOB_SEEKER", "EMPLOYER"}:
                return self._route_smart_job(sender_mobile, clean_message, intent)

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

    def _route_smart_job(self, sender_mobile: str, message: str, intent: str) -> str:
        details = self.smart_job_message_service.extract(message)
        session = self.session_registry.get(sender_mobile)
        session.data.clear()

        if intent == "JOB_SEEKER":
            session.data["role"] = "WORKER"
            if details.get("category"):
                session.data["category"] = details["category"]
            if details.get("experience"):
                session.data["experience"] = details["experience"]
            if details.get("availability"):
                session.data["availability"] = details["availability"]

            if not session.data.get("category"):
                session.step = ConversationStep.WORKER_CATEGORY
                return self._reply(sender_mobile, self._category_menu())
            if not session.data.get("experience"):
                session.step = ConversationStep.WORKER_EXPERIENCE
                return self._reply(
                    sender_mobile,
                    f"✅ {session.data['category']} పని అర్థమైంది. మీ Experience ఎంత?\n"
                    "1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years",
                )
            if not session.data.get("availability"):
                session.step = ConversationStep.WORKER_AVAILABILITY
                return self._reply(
                    sender_mobile,
                    "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week",
                )

            self.user_repository.save_worker_profile(
                whatsapp_mobile=sender_mobile,
                category=session.data["category"],
                experience=session.data["experience"],
                availability=session.data["availability"],
            )
            session.step = ConversationStep.WORKER_LOCATION
            return self._reply(
                sender_mobile,
                "✅ మీ పని వివరాలు తీసుకున్నాను. 📍 ఇప్పుడు WhatsApp Attachment ద్వారా Current Location share చేయండి.",
            )

        session.data["role"] = "EMPLOYER"
        if details.get("category"):
            session.data["service"] = details["category"]

        if not session.data.get("service"):
            if len(message.split()) >= 4:
                session.data["pending_requirement"] = message
            session.step = ConversationStep.EMPLOYER_SERVICE
            return self._reply(sender_mobile, self._employer_service_menu())

        self.user_repository.save_employer_post(
            whatsapp_mobile=sender_mobile,
            service=session.data["service"],
            requirement=message,
        )
        session.data["requirement"] = message
        session.step = ConversationStep.EMPLOYER_LOCATION
        return self._reply(
            sender_mobile,
            f"✅ {session.data['service']} requirement అర్థమైంది. 📍 ఇప్పుడు WhatsApp Attachment ద్వారా Job Location share చేయండి.",
        )
