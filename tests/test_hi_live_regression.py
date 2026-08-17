from app.models.session import ConversationStep
from app.services.marketplace_conversation_service import MarketplaceConversationService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.MAIN_MENU
        self.data = {}


class FakeRegistry:
    def __init__(self):
        self.session = FakeSession()

    def get(self, sender_mobile):
        return self.session

    def save(self, sender_mobile):
        return None

    def reset(self, sender_mobile):
        self.session = FakeSession()


class FakeUsers:
    def find_by_whatsapp_mobile(self, sender_mobile):
        return {
            "registration_complete": 1,
            "name": "Live Test User",
            "entered_mobile": "9999999999",
            "area": "Vijayawada",
            "capabilities": ["BUYER"],
        }

    def list_capabilities(self, sender_mobile):
        return ["BUYER"]


class ExplodingRouter:
    def classify(self, message):
        raise RuntimeError("AI classifier must never run for Hi")


class FakeMarketplace:
    pass


def test_registered_hi_bypasses_ai_classifier_and_returns_main_menu():
    service = MarketplaceConversationService(
        user_repository=FakeUsers(),
        session_registry=FakeRegistry(),
        intent_router=ExplodingRouter(),
        marketplace_repository=FakeMarketplace(),
    )

    reply = service.process("9199", "Hi")

    assert "మీకు ఏ విధంగా సహాయం చేయాలి" in reply
