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
        if "అపాయింట్మెంట్" in message:
            return {"intent": "APPOINTMENT", "source": "rules", "confidence": 1.0}
        if "పని కావాలి" in message:
            return {"intent": "JOB_SEEKER", "source": "rules", "confidence": 1.0}
        if "వర్కర్స్ కావాలి" in message:
            return {"intent": "EMPLOYER", "source": "rules", "confidence": 1.0}
        return {"intent": "UNKNOWN", "source": "rules", "confidence": 0.0}


class FakeAppointmentService:
    def __init__(self):
        self.started = []
        self.processed = []

    def start(self, sender_mobile, initial_message=""):
        self.started.append((sender_mobile, initial_message))
        return "APPOINTMENT_STARTED"

    def process(self, sender_mobile, message):
        self.processed.append((sender_mobile, message))
        return "APPOINTMENT_CONSUMED"


def make_service(step=ConversationStep.WORKER_CATEGORY):
    registry = FakeRegistry()
    registry.session.step = step
    appointment_service = FakeAppointmentService()
    service = IntentAwareConversationService(
        user_repository=FakeUserRepository(),
        session_registry=registry,
        intent_router=FakeRouter(),
        appointment_service=appointment_service,
    )
    return service, registry, appointment_service


def test_clear_appointment_request_can_leave_worker_category_menu():
    service, registry, appointment_service = make_service()
    message = "సెలూన్ కోసం అపాయింట్మెంట్ కావాలి"

    result = service.process("9199", message)

    assert result == "APPOINTMENT_STARTED"
    assert appointment_service.started == [("9199", message)]


def test_job_seeker_intent_exits_appointment_time_without_saving_as_time():
    service, registry, appointment_service = make_service(ConversationStep.APPOINTMENT_TIME)
    registry.session.data = {"appointment_category": "Salon", "appointment_date": "Tomorrow"}

    result = service.process("9199", "నాకు పని కావాలి")

    assert "మీరు ఏ పని కోసం చూస్తున్నారు?" in result
    assert registry.session.step == ConversationStep.WORKER_CATEGORY
    assert registry.session.data == {"role": "WORKER"}
    assert appointment_service.processed == []


def test_employer_intent_exits_appointment_flow():
    service, registry, appointment_service = make_service(ConversationStep.APPOINTMENT_DATE)
    registry.session.data = {"appointment_category": "Salon"}

    result = service.process("9199", "వర్కర్స్ కావాలి")

    assert "Employer workflow" in result
    assert registry.session.step == ConversationStep.EMPLOYER_SERVICE
    assert registry.session.data == {"role": "EMPLOYER"}
    assert appointment_service.processed == []
