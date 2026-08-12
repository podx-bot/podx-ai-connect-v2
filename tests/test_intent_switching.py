from app.models.session import ConversationStep
from app.services.intent_aware_conversation_service import IntentAwareConversationService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.WORKER_CATEGORY
        self.data = {"role": "worker"}


class FakeRegistry:
    def __init__(self):
        self.session = FakeSession()
        self.saved = []

    def get(self, sender_mobile):
        return self.session

    def save(self, sender_mobile):
        self.saved.append(sender_mobile)


class FakeUserRepository:
    def find_by_whatsapp_mobile(self, sender_mobile):
        return {"registration_complete": 1}


class FakeRouter:
    def classify(self, message):
        assert "అపాయింట్మెంట్" in message
        return {"intent": "APPOINTMENT", "source": "rules", "confidence": 1.0}


class FakeAppointmentService:
    def __init__(self):
        self.started = []

    def start(self, sender_mobile, initial_message=""):
        self.started.append((sender_mobile, initial_message))
        return "APPOINTMENT_STARTED"

    def process(self, sender_mobile, message):
        return None


def test_clear_appointment_request_can_leave_worker_category_menu():
    registry = FakeRegistry()
    appointment_service = FakeAppointmentService()
    service = IntentAwareConversationService(
        user_repository=FakeUserRepository(),
        session_registry=registry,
        intent_router=FakeRouter(),
        appointment_service=appointment_service,
    )

    message = "సెలూన్ కోసం అపాయింట్మెంట్ కావాలి"
    result = service.process("9199", message)

    assert result == "APPOINTMENT_STARTED"
    assert appointment_service.started == [("9199", message)]
