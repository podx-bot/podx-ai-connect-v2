from app.models.session import ConversationStep
from app.services.marketplace_conversation_service import MarketplaceConversationService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.MAIN_MENU
        self.data = {}


class FakeRegistry:
    def __init__(self):
        self.session = FakeSession()
        self.saved = []

    def get(self, sender_mobile):
        return self.session

    def save(self, sender_mobile):
        self.saved.append(sender_mobile)

    def reset(self, sender_mobile):
        self.session = FakeSession()


class FakeUserRepository:
    def __init__(self):
        self.capabilities = []
        self.user = {
            "registration_complete": 1,
            "name": "Test User",
            "entered_mobile": "9999999999",
            "area": "Vijayawada",
            "capabilities": [],
        }

    def find_by_whatsapp_mobile(self, sender_mobile):
        result = dict(self.user)
        result["capabilities"] = list(self.capabilities)
        return result

    def add_capability(self, sender_mobile, capability, source="conversation"):
        if capability not in self.capabilities:
            self.capabilities.append(capability)

    def add_capabilities(self, sender_mobile, capabilities, source="registration"):
        for capability in capabilities:
            self.add_capability(sender_mobile, capability, source=source)

    def list_capabilities(self, sender_mobile):
        return list(self.capabilities)


class FakeMarketplaceRepository:
    def __init__(self):
        self.seller_listings = []
        self.provider_profiles = []

    def save_seller_listing(self, **kwargs):
        self.seller_listings.append(kwargs)
        return len(self.seller_listings)

    def save_service_provider_profile(self, **kwargs):
        self.provider_profiles.append(kwargs)
        return len(self.provider_profiles)


class FakeRouter:
    def classify(self, message):
        lowered = message.lower()
        if "products అమ్ముతాను" in lowered:
            return {"intent": "SELL_PRODUCT", "source": "rules", "confidence": 1.0}
        if "electrician service చేస్తాను" in lowered:
            return {"intent": "SERVICE_PROVIDER", "source": "rules", "confidence": 1.0}
        return {"intent": "UNKNOWN", "source": "rules", "confidence": 0.0}


def build_service():
    users = FakeUserRepository()
    registry = FakeRegistry()
    marketplace = FakeMarketplaceRepository()
    service = MarketplaceConversationService(
        user_repository=users,
        session_registry=registry,
        intent_router=FakeRouter(),
        marketplace_repository=marketplace,
    )
    return service, users, registry, marketplace


def test_seller_requires_confirmation_before_saving_listing():
    service, users, registry, marketplace = build_service()

    response = service.process("9199", "నేను products అమ్ముతాను")
    assert "Seller" in response
    assert registry.session.step == ConversationStep.SELLER_PRODUCT_NAME

    service.process("9199", "Chicken")
    assert registry.session.step == ConversationStep.SELLER_PRODUCT_PRICE

    response = service.process("9199", "₹250/kg")
    assert "Save చేసే ముందు" in response
    assert registry.session.step == ConversationStep.SELLER_CONFIRM
    assert marketplace.seller_listings == []
    assert "SELLER" not in users.capabilities

    response = service.process("9199", "1")
    assert "Seller listing save" in response
    assert registry.session.step == ConversationStep.MAIN_MENU
    assert "SELLER" in users.capabilities
    assert marketplace.seller_listings[0]["product_name"] == "Chicken"
    assert marketplace.seller_listings[0]["price_text"] == "₹250/kg"
    assert marketplace.seller_listings[0]["area"] == "Vijayawada"


def test_seller_edit_does_not_save_wrong_voice_transcription():
    service, users, registry, marketplace = build_service()

    service.process("9199", "నేను products అమ్ముతాను")
    service.process("9199", "చికెన్ అమృతాను")
    service.process("9199", "రెండొందల యాభై కేజీ")

    assert registry.session.step == ConversationStep.SELLER_CONFIRM
    assert marketplace.seller_listings == []

    response = service.process("9199", "2")
    assert "మళ్లీ" in response
    assert registry.session.step == ConversationStep.SELLER_PRODUCT_NAME
    assert marketplace.seller_listings == []
    assert "SELLER" not in users.capabilities

    service.process("9199", "Chicken")
    service.process("9199", "₹250/kg")
    service.process("9199", "yes")

    assert marketplace.seller_listings[0]["product_name"] == "Chicken"
    assert marketplace.seller_listings[0]["price_text"] == "₹250/kg"


def test_service_provider_requires_confirmation_before_saving_profile():
    service, users, registry, marketplace = build_service()

    response = service.process("9199", "నేను electrician service చేస్తాను")
    assert "Service Provider" in response
    assert registry.session.step == ConversationStep.SERVICE_PROVIDER_NAME

    service.process("9199", "Electrician")
    assert registry.session.step == ConversationStep.SERVICE_PROVIDER_DETAILS

    response = service.process("9199", "Home wiring, ₹500 onwards")
    assert "Save చేసే ముందు" in response
    assert registry.session.step == ConversationStep.SERVICE_PROVIDER_CONFIRM
    assert marketplace.provider_profiles == []

    response = service.process("9199", "అవును")
    assert "Service Provider profile save" in response
    assert registry.session.step == ConversationStep.MAIN_MENU
    assert "SERVICE_PROVIDER" in users.capabilities
    assert marketplace.provider_profiles[0]["service_name"] == "Electrician"
    assert marketplace.provider_profiles[0]["details"] == "Home wiring, ₹500 onwards"
    assert marketplace.provider_profiles[0]["area"] == "Vijayawada"


def test_invalid_confirmation_keeps_confirmation_state():
    service, _, registry, marketplace = build_service()

    service.process("9199", "నేను products అమ్ముతాను")
    service.process("9199", "Chicken")
    service.process("9199", "₹250/kg")
    response = service.process("9199", "maybe")

    assert "1. Yes" in response
    assert registry.session.step == ConversationStep.SELLER_CONFIRM
    assert marketplace.seller_listings == []


def test_marketplace_layer_preserves_manage_roles_command():
    service, _, registry, _ = build_service()

    response = service.process("9199", "roles")

    assert "current PODX roles" in response
    assert registry.session.step == ConversationStep.WAITING_CAPABILITIES
    assert registry.session.data["manage_roles"] is True
