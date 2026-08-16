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
        ConversationStep.WORKER_EXPERIENCE,
        ConversationStep.WORKER_AVAILABILITY,
        ConversationStep.WORKER_LOCATION,
        ConversationStep.EMPLOYER_SERVICE,
        ConversationStep.EMPLOYER_REQUIREMENT,
        ConversationStep.EMPLOYER_LOCATION,
    }

    APPOINTMENT_INTERRUPT_INTENTS = {
        "JOB_SEEKER",
        "EMPLOYER",
    }

    CLEAR_MENU_INTERRUPT_INTENTS = {
        "JOB_SEEKER",
        "EMPLOYER",
        "APPOINTMENT",
        "SERVICE",
        "SHOP_PRODUCT",
    }

    SMART_WORKER_STEPS = {
        ConversationStep.WORKER_CATEGORY,
        ConversationStep.WORKER_EXPERIENCE,
        ConversationStep.WORKER_AVAILABILITY,
    }

    SHORT_WORKER_CATEGORY_PROMPT = (
        "ఏ పని కావాలో పేరు చెప్పండి. ఉదా: Delivery, Catering, Driver లేదా Cleaning."
    )

    def __init__(
        self,
        user_repository,
        session_registry,
        intent_router: IntentRouterService,
        appointment_service=None,
        demand_capture_service=None,
    ) -> None:
        super().__init__(user_repository=user_repository, session_registry=session_registry)
        self.intent_router = intent_router
        self.appointment_service = appointment_service
        self.demand_capture_service = demand_capture_service
        self.smart_job_message_service = SmartJobMessageService()

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(existing_user and existing_user.get("registration_complete") == 1)

        rule_classifier = getattr(self.intent_router, "_classify_rules", None)
        rule_intent = rule_classifier(clean_message) if registered and callable(rule_classifier) else None

        if registered and session.step == ConversationStep.WORKER_CATEGORY:
            active_reply = self._handle_active_worker_category(
                sender_mobile=sender_mobile,
                message=clean_message,
                detected_intent=rule_intent,
            )
            if active_reply is not None:
                return active_reply

        # A clear new request is allowed to leave stale worker/employer menus.
        # Only deterministic rule matches interrupt; unknown text and normal
        # numeric/form answers stay inside the active workflow.
        if (
            registered
            and session.step in self.INTENT_SWITCH_STEPS
            and session.step not in {ConversationStep.START, ConversationStep.MAIN_MENU}
            and rule_intent in self.CLEAR_MENU_INTERRUPT_INTENTS
        ):
            if rule_intent == "APPOINTMENT" and self.appointment_service:
                session.data.clear()
                return self.appointment_service.start(sender_mobile, initial_message=clean_message)
            if rule_intent in {"JOB_SEEKER", "EMPLOYER"}:
                return self._route_smart_job(sender_mobile, clean_message, rule_intent)
            if rule_intent == "SERVICE":
                session.data.clear()
                session.step = ConversationStep.MAIN_MENU
                self._record_capability(sender_mobile, "SERVICE_CUSTOMER")
                self._capture_unresolved_demand(
                    sender_mobile=sender_mobile,
                    intent=rule_intent,
                    message=clean_message,
                    existing_user=existing_user,
                )
                return self._reply(
                    sender_mobile,
                    "🛠️ Service request save చేశాను. Provider match దొరికినప్పుడు PODX connect చేస్తుంది.",
                )
            if rule_intent == "SHOP_PRODUCT":
                session.data.clear()
                session.step = ConversationStep.MAIN_MENU
                self._record_capability(sender_mobile, "BUYER")
                self._capture_unresolved_demand(
                    sender_mobile=sender_mobile,
                    intent=rule_intent,
                    message=clean_message,
                    existing_user=existing_user,
                )
                return self._reply(
                    sender_mobile,
                    "🛍️ Product request save చేశాను. Seller/stock match దొరికినప్పుడు PODX connect చేస్తుంది.",
                )

        if registered and session.data.get("smart_prefill"):
            if session.step in self.SMART_WORKER_STEPS:
                smart_reply = self._continue_smart_worker(sender_mobile, clean_message)
                if smart_reply is not None:
                    return smart_reply
            if session.step == ConversationStep.EMPLOYER_SERVICE:
                smart_reply = self._continue_smart_employer(sender_mobile, clean_message)
                if smart_reply is not None:
                    return smart_reply

        if self.appointment_service and session.step in self.APPOINTMENT_STEPS:
            interrupt_intent = rule_intent
            if registered and interrupt_intent in self.APPOINTMENT_INTERRUPT_INTENTS:
                return self._route_smart_job(sender_mobile, clean_message, interrupt_intent)
            appointment_reply = self.appointment_service.process(sender_mobile, clean_message)
            if appointment_reply is not None:
                return appointment_reply

        router_allowed = registered and session.step in self.INTENT_SWITCH_STEPS
        if router_allowed:
            classification = self.intent_router.classify(clean_message)
            intent = classification.get("intent", "UNKNOWN")
            if (
                session.step == ConversationStep.WORKER_CATEGORY
                and intent == "JOB_SEEKER"
            ):
                return self._reply(sender_mobile, self.SHORT_WORKER_CATEGORY_PROMPT)
            if intent == "APPOINTMENT" and self.appointment_service:
                return self.appointment_service.start(sender_mobile, initial_message=clean_message)
            if intent in {"JOB_SEEKER", "EMPLOYER"}:
                return self._route_smart_job(sender_mobile, clean_message, intent)
            if session.step in {ConversationStep.START, ConversationStep.MAIN_MENU}:
                routed_command = self.ROUTED_COMMANDS.get(intent)
                if routed_command:
                    return super().process(sender_mobile, routed_command)
                if intent == "SERVICE":
                    self._record_capability(sender_mobile, "SERVICE_CUSTOMER")
                    self._capture_unresolved_demand(
                        sender_mobile=sender_mobile,
                        intent=intent,
                        message=clean_message,
                        existing_user=existing_user,
                    )
                    return self._reply(
                        sender_mobile,
                        "🛠️ మీ local service request save చేశాను. ప్రస్తుతం direct match దొరకకపోతే PODX ఈ demandని track చేసి provider available అయినప్పుడు connect చేయగలదు.",
                    )
                if intent == "SHOP_PRODUCT":
                    self._record_capability(sender_mobile, "BUYER")
                    self._capture_unresolved_demand(
                        sender_mobile=sender_mobile,
                        intent=intent,
                        message=clean_message,
                        existing_user=existing_user,
                    )
                    return self._reply(
                        sender_mobile,
                        "🛍️ మీ product request save చేశాను. ప్రస్తుతం local match దొరకకపోతే PODX ఈ demandని track చేసి seller/stock available అయినప్పుడు connect చేయగలదు.",
                    )

        if registered and session.step == ConversationStep.WORKER_CATEGORY:
            normalized = clean_message.lower()
            explicit_menu = normalized in {"menu", "main menu", "మెను", "మెనూ"}
            category = self.CATEGORY_MAP.get(normalized)
            if category is None:
                category = self.smart_job_message_service.extract(clean_message).get("category")
            if not explicit_menu and category is None:
                return self._reply(sender_mobile, self.SHORT_WORKER_CATEGORY_PROMPT)

        return super().process(sender_mobile, clean_message)

    def _handle_active_worker_category(
        self,
        sender_mobile: str,
        message: str,
        detected_intent: str | None,
    ) -> str | None:
        normalized = message.lower()
        if normalized in {"menu", "main menu", "మెను", "మెనూ"}:
            return None

        if (
            detected_intent in self.CLEAR_MENU_INTERRUPT_INTENTS
            and detected_intent != "JOB_SEEKER"
        ):
            return None

        category = self.CATEGORY_MAP.get(normalized)
        if category is None:
            category = self.smart_job_message_service.extract(message).get("category")

        if category is not None:
            session = self.session_registry.get(sender_mobile)
            session.data.setdefault("role", "WORKER")
            session.data["category"] = category
            return self._next_worker_prompt_or_save(sender_mobile)

        if detected_intent == "JOB_SEEKER":
            return self._reply(sender_mobile, self.SHORT_WORKER_CATEGORY_PROMPT)

        return None

    def _record_capability(self, sender_mobile: str, capability: str) -> None:
        add_capability = getattr(self.user_repository, "add_capability", None)
        if callable(add_capability):
            add_capability(sender_mobile, capability, source="conversation")

    def _capture_unresolved_demand(self, sender_mobile: str, intent: str, message: str, existing_user) -> None:
        if self.demand_capture_service is None:
            return
        location_text = None
        if existing_user:
            location_text = existing_user.get("area") or existing_user.get("location_name")
        self.demand_capture_service.capture_unresolved(
            user_mobile=sender_mobile,
            intent=intent,
            source_message=message,
            location_text=location_text,
            structured_fields={"raw_intent": intent},
        )

    def _route_smart_job(self, sender_mobile: str, message: str, intent: str) -> str:
        details = self.smart_job_message_service.extract(message)
        session = self.session_registry.get(sender_mobile)
        session.data.clear()

        if intent == "JOB_SEEKER":
            self._record_capability(sender_mobile, "WORKER")
            session.data["role"] = "WORKER"
            if details.get("category"):
                session.data["category"] = details["category"]
            if details.get("experience"):
                session.data["experience"] = details["experience"]
            if details.get("availability"):
                session.data["availability"] = details["availability"]
            if any(details.get(key) for key in ("category", "experience", "availability")):
                session.data["smart_prefill"] = True
            return self._next_worker_prompt_or_save(sender_mobile)

        self._record_capability(sender_mobile, "EMPLOYER")
        session.data["role"] = "EMPLOYER"
        if details.get("category"):
            session.data["service"] = details["category"]

        if not session.data.get("service"):
            if len(message.split()) >= 4:
                session.data["pending_requirement"] = message
                session.data["smart_prefill"] = True
            session.step = ConversationStep.EMPLOYER_SERVICE
            prefix = "👷 Employer workflow ప్రారంభమవుతుంది.\n\n" if not session.data.get("smart_prefill") else ""
            return self._reply(sender_mobile, prefix + self._employer_service_menu())

        self.user_repository.save_employer_post(whatsapp_mobile=sender_mobile, service=session.data["service"], requirement=message)
        session.data["requirement"] = message
        session.step = ConversationStep.EMPLOYER_LOCATION
        return self._reply(sender_mobile, f"✅ {session.data['service']} requirement అర్థమైంది. 📍 ఇప్పుడు WhatsApp Attachment ద్వారా Job Location share చేయండి.")

    def _continue_smart_worker(self, sender_mobile: str, message: str) -> str | None:
        session = self.session_registry.get(sender_mobile)
        normalized = message.lower()
        if session.step == ConversationStep.WORKER_CATEGORY:
            value = self.CATEGORY_MAP.get(normalized)
            if value is None:
                value = self.smart_job_message_service.extract(message).get("category")
            if value is None:
                return self._reply(sender_mobile, self.SHORT_WORKER_CATEGORY_PROMPT)
            session.data["category"] = value
            return self._next_worker_prompt_or_save(sender_mobile)
        if session.step == ConversationStep.WORKER_EXPERIENCE:
            value = self.EXPERIENCE_MAP.get(normalized)
            if value is None:
                value = self.smart_job_message_service.extract(message).get("experience")
            if value is None:
                return self._reply(sender_mobile, "మీ Experience ఎంత?\n1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years")
            session.data["experience"] = value
            return self._next_worker_prompt_or_save(sender_mobile)
        if session.step == ConversationStep.WORKER_AVAILABILITY:
            value = self.AVAILABILITY_MAP.get(normalized)
            if value is None:
                value = self.smart_job_message_service.extract(message).get("availability")
            if value is None:
                return self._reply(sender_mobile, "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week")
            session.data["availability"] = value
            return self._next_worker_prompt_or_save(sender_mobile)
        return None

    def _next_worker_prompt_or_save(self, sender_mobile: str) -> str:
        session = self.session_registry.get(sender_mobile)
        if not session.data.get("category"):
            session.step = ConversationStep.WORKER_CATEGORY
            return self._reply(sender_mobile, self._category_menu())
        if not session.data.get("experience"):
            session.step = ConversationStep.WORKER_EXPERIENCE
            return self._reply(sender_mobile, f"✅ {session.data['category']} పని అర్థమైంది. మీ Experience ఎంత?\n1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years")
        if not session.data.get("availability"):
            session.step = ConversationStep.WORKER_AVAILABILITY
            return self._reply(sender_mobile, "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week")
        self.user_repository.save_worker_profile(whatsapp_mobile=sender_mobile, category=session.data["category"], experience=session.data["experience"], availability=session.data["availability"])
        session.data.pop("smart_prefill", None)
        session.step = ConversationStep.WORKER_LOCATION
        return self._reply(sender_mobile, "✅ మీ పని వివరాలు తీసుకున్నాను. 📍 ఇప్పుడు WhatsApp Attachment ద్వారా మీ Current Location share చేయండి.")

    def _continue_smart_employer(self, sender_mobile: str, message: str) -> str | None:
        session = self.session_registry.get(sender_mobile)
        if session.step != ConversationStep.EMPLOYER_SERVICE:
            return None
        normalized = message.lower()
        service = self.SERVICE_MAP.get(normalized)
        if service is None:
            service = self.smart_job_message_service.extract(message).get("category")
        if service is None:
            return None
        session.data["service"] = service
        requirement = session.data.pop("pending_requirement", None)
        if requirement:
            self.user_repository.save_employer_post(whatsapp_mobile=sender_mobile, service=service, requirement=requirement)
            session.data["requirement"] = requirement
            session.data.pop("smart_prefill", None)
            session.step = ConversationStep.EMPLOYER_LOCATION
            return self._reply(sender_mobile, f"✅ {service} requirement అర్థమైంది. 📍 ఇప్పుడు WhatsApp Attachment ద్వారా Job Location share చేయండి.")
        return None
