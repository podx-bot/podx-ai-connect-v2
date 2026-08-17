from app.models.session import ConversationStep
from app.services.role_aware_conversation_service import RoleAwareConversationService


class MarketplaceConversationService(RoleAwareConversationService):
    """Handle seller and service-provider onboarding from natural language intents."""

    COMPLETION_SKIP_WORDS = {"skip", "later", "తెలియదు", "తర్వాత", "వద్దు", "n/a"}
    CONFIRM_WORDS = {"1", "yes", "y", "ok", "okay", "correct", "అవును", "సరే", "కరెక్ట్"}
    EDIT_WORDS = {"2", "edit", "change", "no", "n", "కాదు", "మార్చు", "ఎడిట్"}
    GREETING_WORDS = {"hi", "hello", "hey", "హాయ్", "హలో"}

    def __init__(self, user_repository, session_registry, intent_router, marketplace_repository, appointment_service=None, demand_capture_service=None) -> None:
        super().__init__(user_repository=user_repository, session_registry=session_registry, intent_router=intent_router, appointment_service=appointment_service, demand_capture_service=demand_capture_service)
        self.marketplace_repository = marketplace_repository

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        normalized = clean_message.lower()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(existing_user and existing_user.get("registration_complete") == 1)

        # Greetings are deterministic control messages. Never send a registered
        # user's Hi through an external AI classifier: a provider outage must not
        # be able to break the most basic entry point into PODX.
        if registered and normalized in self.GREETING_WORDS:
            session.step = ConversationStep.MAIN_MENU
            session.data.clear()
            return self._reply(sender_mobile, self._main_menu())

        if registered and self.appointment_service is not None:
            appointment_command = self.appointment_service.process_provider_command(sender_mobile, clean_message)
            if appointment_command is not None:
                return self._reply(sender_mobile, appointment_command)

        if registered and normalized in self.ROLE_COMMANDS:
            return super().process(sender_mobile, clean_message)

        if registered and session.step == ConversationStep.SELLER_PRODUCT_NAME:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "మీరు అమ్మే product పేరు పంపండి.")
            session.data["product_name"] = clean_message
            session.step = ConversationStep.SELLER_PRODUCT_PRICE
            return self._reply(sender_mobile, f"✅ Product: {clean_message}\n\nధర / price ఎంత? ఉదాహరణ: ₹250 లేదా ₹250/kg. ధర తర్వాత చెప్పాలంటే Skip పంపండి.")

        if registered and session.step == ConversationStep.SELLER_PRODUCT_PRICE:
            price_text = None if normalized in self.COMPLETION_SKIP_WORDS else clean_message
            if price_text is not None and not price_text:
                return self._reply(sender_mobile, "ధర పంపండి లేదా Skip పంపండి.")
            session.data["pending_price_text"] = price_text
            session.step = ConversationStep.SELLER_CONFIRM
            return self._reply(sender_mobile, self._seller_confirmation_text(session.data["product_name"], price_text))

        if registered and session.step == ConversationStep.SELLER_CONFIRM:
            if normalized in self.CONFIRM_WORDS:
                return self._save_seller_listing(sender_mobile, session, existing_user)
            if normalized in self.EDIT_WORDS:
                session.data.pop("product_name", None)
                session.data.pop("pending_price_text", None)
                session.step = ConversationStep.SELLER_PRODUCT_NAME
                return self._reply(sender_mobile, "✏️ సరే. మళ్లీ మీరు అమ్మే product పేరు పంపండి.")
            return self._reply(sender_mobile, "దయచేసి confirm చేయండి:\n1. Yes ✅\n2. Edit ✏️")

        if registered and session.step == ConversationStep.SERVICE_PROVIDER_NAME:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "మీరు ఇచ్చే service పేరు పంపండి. ఉదాహరణ: Electrician, Plumbing, AC Repair.")
            session.data["service_name"] = clean_message
            session.step = ConversationStep.SERVICE_PROVIDER_DETAILS
            return self._reply(sender_mobile, f"✅ Service: {clean_message}\n\nమీ service గురించి చిన్న details / rate / availability పంపండి. ఇప్పుడే వద్దంటే Skip పంపండి.")

        if registered and session.step == ConversationStep.SERVICE_PROVIDER_DETAILS:
            details = None if normalized in self.COMPLETION_SKIP_WORDS else clean_message
            if details is not None and not details:
                return self._reply(sender_mobile, "Service details పంపండి లేదా Skip పంపండి.")
            session.data["pending_service_details"] = details
            session.step = ConversationStep.SERVICE_PROVIDER_CONFIRM
            return self._reply(sender_mobile, self._provider_confirmation_text(session.data["service_name"], details))

        if registered and session.step == ConversationStep.SERVICE_PROVIDER_CONFIRM:
            if normalized in self.CONFIRM_WORDS:
                return self._save_service_provider(sender_mobile, session, existing_user)
            if normalized in self.EDIT_WORDS:
                session.data.pop("service_name", None)
                session.data.pop("pending_service_details", None)
                session.step = ConversationStep.SERVICE_PROVIDER_NAME
                return self._reply(sender_mobile, "✏️ సరే. మళ్లీ మీరు ఇచ్చే service పేరు పంపండి.")
            return self._reply(sender_mobile, "దయచేసి confirm చేయండి:\n1. Yes ✅\n2. Edit ✏️")

        if registered and session.step in {ConversationStep.START, ConversationStep.MAIN_MENU}:
            classification = self.intent_router.classify(clean_message)
            intent = classification.get("intent", "UNKNOWN")
            if intent == "SELL_PRODUCT":
                session.data.clear()
                session.data["source_message"] = clean_message
                session.step = ConversationStep.SELLER_PRODUCT_NAME
                return self._reply(sender_mobile, "🛍️ మీరు Sellerగా add అవుతున్నారు.\n\nమీరు అమ్మే product పేరు పంపండి. ఉదాహరణ: Chicken, Rice, Mobile Accessories.")
            if intent == "SERVICE_PROVIDER":
                session.data.clear()
                session.data["source_message"] = clean_message
                session.step = ConversationStep.SERVICE_PROVIDER_NAME
                return self._reply(sender_mobile, "🛠️ మీరు Service Providerగా add అవుతున్నారు.\n\nమీరు ఇచ్చే service పేరు పంపండి. ఉదాహరణ: Electrician, Plumbing, AC Repair.")
            if intent == "UNKNOWN":
                return self._reply(sender_mobile, self._clarification_prompt())

        return super().process(sender_mobile, clean_message)

    @staticmethod
    def _clarification_prompt() -> str:
        return (
            "🤔 మీ అవసరం పూర్తిగా అర్థం కాలేదు. ఇంకొంచెం స్పష్టంగా ఒక చిన్న వాక్యంలో చెప్పండి లేదా voice పంపండి.\n\n"
            "ఉదా: Electrician కావాలి / Chicken కొనాలి / ఉద్యోగం కావాలి / workers కావాలి."
        )

    @staticmethod
    def _main_menu() -> str:
        return (
            "👋 మీకు ఏ విధంగా సహాయం చేయాలి?\n\n"
            "మీకు కావాల్సింది మీ మాటల్లో చెప్పండి — 🎙️ voiceగా లేదా ⌨️ textగా.\n\n"
            "ఉదాహరణలు:\n"
            "• నాకు ఉద్యోగం కావాలి\n"
            "• నాకు workers కావాలి\n"
            "• Chicken కొనాలి\n"
            "• నేను Chicken అమ్ముతాను\n"
            "• Electrician కావాలి\n"
            "• నేను Electrician service చేస్తాను\n\n"
            "PODX మీ అవసరాన్ని అర్థం చేసుకుని సరైన flowకి తీసుకెళ్తుంది.\n"
            "Options కావాలంటే Menu అని పంపండి."
        )

    @staticmethod
    def _seller_confirmation_text(product_name: str, price_text: str | None) -> str:
        return "🔎 Save చేసే ముందు ఒకసారి check చేయండి.\n\n" + f"Product: {product_name}\nPrice: {price_text or 'Price later'}\n\n" + "ఇవి సరైనవేనా?\n1. Yes ✅\n2. Edit ✏️"

    @staticmethod
    def _provider_confirmation_text(service_name: str, details: str | None) -> str:
        return "🔎 Save చేసే ముందు ఒకసారి check చేయండి.\n\n" + f"Service: {service_name}\nDetails: {details or 'Details later'}\n\n" + "ఇవి సరైనవేనా?\n1. Yes ✅\n2. Edit ✏️"

    def _save_seller_listing(self, sender_mobile, session, existing_user) -> str:
        area = (existing_user or {}).get("area") or (existing_user or {}).get("location_name")
        product_name = session.data["product_name"]
        price_text = session.data.get("pending_price_text")
        self.marketplace_repository.save_seller_listing(seller_mobile=sender_mobile, product_name=product_name, price_text=price_text, area=area, source_message=session.data.get("source_message"))
        self._record_capability(sender_mobile, "SELLER")
        session.data.clear()
        session.step = ConversationStep.MAIN_MENU
        return self._reply(sender_mobile, f"✅ Seller listing save అయింది.\nProduct: {product_name}\nPrice: {price_text or 'Price later'}\nArea: {area or '-'}\n\n" + self._main_menu())

    def _save_service_provider(self, sender_mobile, session, existing_user) -> str:
        area = (existing_user or {}).get("area") or (existing_user or {}).get("location_name")
        service_name = session.data["service_name"]
        details = session.data.get("pending_service_details")
        self.marketplace_repository.save_service_provider_profile(provider_mobile=sender_mobile, service_name=service_name, details=details, area=area, source_message=session.data.get("source_message"))
        self._record_capability(sender_mobile, "SERVICE_PROVIDER")
        session.data.clear()
        session.step = ConversationStep.MAIN_MENU
        return self._reply(sender_mobile, f"✅ Service Provider profile save అయింది.\nService: {service_name}\nDetails: {details or 'Details later'}\nArea: {area or '-'}\n\n" + self._main_menu())
