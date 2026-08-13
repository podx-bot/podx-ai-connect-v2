from app.models.session import ConversationStep
from app.services.role_aware_conversation_service import RoleAwareConversationService


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


class FakeUserRepository:
    def __init__(self):
        self.capabilities = []

    def find_by_whatsapp_mobile(self, sender_mobile):
        return {
            "registration_complete": 1,
            "capabilities": list(self.capabilities),
        }

    def add_capabilities(self, sender_mobile, capabilities, source="registration"):
        for capability in capabilities:
            if capability not in self.capabilities:
                self.capabilities.append(capability)

    def list_capabilities(self, sender_mobile):
        return sorted(self.capabilities)


class FakeRouter:
    def classify(self, message):
        return {"intent": "UNKNOWN"}


def build_service():
    repository = FakeUserRepository()
    registry = FakeRegistry()
    service = RoleAwareConversationService(
        user_repository=repository,
        session_registry=registry,
        intent_router=FakeRouter(),
    )
    return service, repository, registry


def test_existing_user_can_open_manage_roles_and_add_multiple_capabilities():
    service, repository, registry = build_service()

    response = service.process("9199", "roles")
    assert "current PODX roles" in response
    assert registry.session.step == ConversationStep.WAITING_CAPABILITIES
    assert registry.session.data["manage_roles"] is True

    response = service.process("9199", "1,2,4,5")
    assert "roles update" in response
    assert repository.capabilities == [
        "BUYER",
        "SELLER",
        "SERVICE_PROVIDER",
        "WORKER",
    ]
    assert registry.session.step == ConversationStep.MAIN_MENU
    assert registry.session.data == {}


def test_manage_roles_is_additive_and_does_not_remove_existing_role():
    service, repository, _ = build_service()
    repository.capabilities = ["WORKER"]

    service.process("9199", "నా రోల్స్")
    service.process("9199", "1,2")

    assert set(repository.capabilities) == {"WORKER", "BUYER", "SELLER"}
