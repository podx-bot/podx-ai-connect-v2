from app.models.session import ConversationStep
from app.services.role_aware_conversation_service import RoleAwareConversationService


class MarketplaceConversationService(RoleAwareConversationService):
    """Handle seller and service-provider onboarding from natural language intents."""

    COMPLETION_SKIP_WORDS = {"skip", "later", "తెలియదు", "తర్వాత", "వద్దు", "n/a"}

    def __init__(
        self,
        user_repository,
        session_registry,
        intent_router,
        marketplace_repository,
        appointment_service=None,
        demand_capture_service=None,
    ) -> None:
        super().__init__(
            user_repository=user_repository,
            session_registry=session_registry,
            intent_router=intent_router,
            appointment_service=appointment_service,
            demand_capture_service=demand_capture_service,
        )
        self.marketplace_repository = marketplace_repository

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        normalized = clean_message.lower()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(existing_user and existing_user.get("registration_complete") == 1)

        if registered and session.step == ConversationStep.SELLER_PRODUCT_NAME:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "మీరు అమ్మే product పేరు పంపండి.")
            session.data["product_name"] = clean_message
            session.step = ConversationStep.SELLER_PRODUCT_PRICE
            return self._reply(
                sender_mobile,
                f"✅ Product: {clean_message}\n\nధర / price ఎంత? ఉదాహరణ: ₹250 లేదా ₹250/kg. ధర తర్వాత చెప్పాలంటే Skip పంపండి.",
            )

        if registered and session.step == ConversationStep.SELLER_PRODUCT_PRICE:
            price_text = None if normalized in self.COMPLETION_SKIP_WORDS else clean_message
            if price_text is not None and not price_text:
                return self._reply(sender_mobile, "ధర పంపండి లేదా Skip పంపండి.")
            area = (existing_user or {}).get("area") or (existing_user or {}).get("location_name")
            self.marketplace_repository.save_seller_listing(
                seller_mobile=sender_mobile,
                product_name=session.data["product_name"],
                price_text=price_text,
                area=area,
                source_message=session.data.get("source_message"),
            )
            self._record_capability(sender_mobile, "SELLER")
            product_name = session.data["product_name"]
            session.data.clear()
            session.step = ConversationStep.MAIN_MENU
            price_display = price_text or "Price later"
            return self._reply(
                sender_mobile,
                f"✅ Seller listing save అయింది.\nProduct: {product_name}\nPrice: {price_display}\nArea: {area or '-'}\n\n"
                + self._main_menu(),
            )

        if registered and session.step == ConversationStep.SERVICE_PROVIDER_NAME:
            if len(clean_message) < 2:
                return self._reply(sender_mobile, "మీరు ఇచ్చే service పేరు పంపండి. ఉదాహరణ: Electrician, Plumbing, AC Repair.")
            session.data["service_name"] = clean_message
            session.step = ConversationStep.SERVICE_PROVIDER_DETAILS
            return self._reply(
                sender_mobile,
                f"✅ Service: {clean_message}\n\nమీ service గురించి చిన్న details / rate / availability పంపండి. ఇప్పుడే వద్దంటే Skip పంపండి.",
            )

        if registered and session.step == ConversationStep.SERVICE_PROVIDER_DETAILS:
            details = None if normalized in self.COMPLETION_SKIP_WORDS else clean_message
            if details is not None and not details:
                return self._reply(sender_mobile, "Service details పంపండి లేదా Skip పంపండి.")
            area = (existing_user or {}).get("area") or (existing_user or {}).get("location_name")
            self.marketplace_repository.save_service_provider_profile(
                provider_mobile=sender_mobile,
                service_name=session.data["service_name"],
                details=details,
                area=area,
                source_message=session.data.get("source_message"),
            )
            self._record_capability(sender_mobile, "SERVICE_PROVIDER")
            service_name = session.data["service_name"]
            session.data.clear()
            session.step = ConversationStep.MAIN_MENU
            details_display = details or "Details later"
            return self._reply(
                sender_mobile,
                f"✅ Service Provider profile save అయింది.\nService: {service_name}\nDetails: {details_display}\nArea: {area or '-'}\n\n"
                + self._main_menu(),
            )

        if registered and session.step in {ConversationStep.START, ConversationStep.MAIN_MENU}:
            classification = self.intent_router.classify(clean_message)
            intent = classification.get("intent", "UNKNOWN")
            if intent == "SELL_PRODUCT":
                session.data.clear()
                session.data["source_message"] = clean_message
                session.step = ConversationStep.SELLER_PRODUCT_NAME
                return self._reply(
                    sender_mobile,
                    "🛍️ మీరు Sellerగా add అవుతున్నారు.\n\nమీరు అమ్మే product పేరు పంపండి. ఉదాహరణ: Chicken, Rice, Mobile Accessories.",
                )
            if intent == "SERVICE_PROVIDER":
                session.data.clear()
                session.data["source_message"] = clean_message
                session.step = ConversationStep.SERVICE_PROVIDER_NAME
                return self._reply(
                    sender_mobile,
                    "🛠️ మీరు Service Providerగా add అవుతున్నారు.\n\nమీరు ఇచ్చే service పేరు పంపండి. ఉదాహరణ: Electrician, Plumbing, AC Repair.",
                )

        return super().process(sender_mobile, clean_message)
