from app.models.session import ConversationStep
from app.services.role_aware_conversation_service import RoleAwareConversationService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.MAIN_MENU
        self.data = {}


class FakeRegistry:
    def __init__(self):
        self.session = FakeSession()

    def get(self, sender_mobile):
        return self.session


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


def test_single_role_choices_stay_in_manage_roles_until_done():
    service, repository, registry = build_service()

    service.process("9199", "roles")
    service.process("9199", "1")
    service.process("9199", "2")
    service.process("9199", "4")

    assert repository.capabilities == ["BUYER", "SELLER", "SERVICE_PROVIDER"]
    assert registry.session.step == ConversationStep.WAITING_CAPABILITIES
    assert registry.session.data["manage_roles"] is True

    service.process("9199", "done")
    assert registry.session.step == ConversationStep.MAIN_MENU
    assert registry.session.data == {}


def test_invalid_number_cannot_escape_manage_roles_state():
    service, repository, registry = build_service()

    service.process("9199", "roles")
    response = service.process("9199", "99")

    assert "valid options" in response
    assert repository.capabilities == []
    assert registry.session.step == ConversationStep.WAITING_CAPABILITIES
    assert registry.session.data["manage_roles"] is True
