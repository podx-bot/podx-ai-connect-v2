from app.models.session import ConversationStep
from app.services.intent_aware_conversation_service import IntentAwareConversationService
from app.services.intent_router_service import IntentRouterService


class FakeSession:
    def __init__(self, step=ConversationStep.WORKER_CATEGORY, data=None):
        self.step = step
        self.data = data if data is not None else {"role": "worker"}


class FakeRegistry:
    def __init__(self, session=None):
        self.session = session or FakeSession()
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

    @staticmethod
    def _classify_rules(message):
        return IntentRouterService._classify_rules(message)


class FakeAppointmentService:
    def __init__(self):
        self.started = []
        self.processed = []

    def start(self, sender_mobile, initial_message=""):
        self.started.append((sender_mobile, initial_message))
        return "APPOINTMENT_STARTED"

    def process(self, sender_mobile, message):
        self.processed.append((sender_mobile, message))
        return "APPOINTMENT_CONTINUED"


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


def test_job_request_interrupts_active_appointment_time_without_being_saved_as_time():
    session = FakeSession(
        step=ConversationStep.APPOINTMENT_TIME,
        data={
            "appointment_category": "Salon",
            "appointment_area": "Current location",
            "appointment_date": "Tomorrow",
        },
    )
    registry = FakeRegistry(session)
    appointment_service = FakeAppointmentService()
    service = IntentAwareConversationService(
        user_repository=FakeUserRepository(),
        session_registry=registry,
        intent_router=FakeRouter(),
        appointment_service=appointment_service,
    )

    result = service.process("9199", "నాకు పని కావాలి")

    assert session.step == ConversationStep.WORKER_CATEGORY
    assert session.data == {"role": "WORKER"}
    assert "Delivery" in result
    assert appointment_service.processed == []


def test_employer_request_interrupts_active_appointment_time():
    session = FakeSession(
        step=ConversationStep.APPOINTMENT_TIME,
        data={"appointment_category": "Salon", "appointment_date": "Tomorrow"},
    )
    registry = FakeRegistry(session)
    appointment_service = FakeAppointmentService()
    service = IntentAwareConversationService(
        user_repository=FakeUserRepository(),
        session_registry=registry,
        intent_router=FakeRouter(),
        appointment_service=appointment_service,
    )

    result = service.process("9199", "నాకు workers కావాలి")

    assert session.step == ConversationStep.EMPLOYER_SERVICE
    assert session.data == {"role": "EMPLOYER"}
    assert "Employer workflow" in result
    assert appointment_service.processed == []


def test_normal_appointment_time_does_not_leave_appointment_flow():
    session = FakeSession(
        step=ConversationStep.APPOINTMENT_TIME,
        data={"appointment_category": "Salon", "appointment_date": "Tomorrow"},
    )
    registry = FakeRegistry(session)
    appointment_service = FakeAppointmentService()
    service = IntentAwareConversationService(
        user_repository=FakeUserRepository(),
        session_registry=registry,
        intent_router=FakeRouter(),
        appointment_service=appointment_service,
    )

    result = service.process("9199", "4:30 PM")

    assert result == "APPOINTMENT_CONTINUED"
    assert appointment_service.processed == [("9199", "4:30 PM")]
