from app.models.session import ConversationStep
from app.services.appointment_service import AppointmentService


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


class FakeRepository:
    def __init__(self):
        self.created = None

    def create_request(self, **kwargs):
        self.created = kwargs
        return {"id": 7, "status": "REQUESTED", **kwargs}


def test_appointment_flow_saves_request():
    registry = FakeRegistry()
    repository = FakeRepository()
    service = AppointmentService(repository, registry)

    assert "Appointment booking" in service.start("9199")
    assert registry.session.step == ConversationStep.APPOINTMENT_CATEGORY

    assert "Salon" in service.process("9199", "3")
    assert registry.session.step == ConversationStep.APPOINTMENT_AREA

    service.process("9199", "Vuyyuru")
    service.process("9199", "Tomorrow")
    result = service.process("9199", "4 PM")

    assert repository.created["category"] == "Salon"
    assert repository.created["area"] == "Vuyyuru"
    assert repository.created["preferred_date"] == "Tomorrow"
    assert repository.created["preferred_time"] == "4 PM"
    assert "Request ID: #7" in result
    assert registry.session.step == ConversationStep.MAIN_MENU
