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
        return {"id": 9, **kwargs}


def test_salon_request_skips_category_menu_and_collects_target_plus_schedule():
    registry = FakeRegistry()
    repository = FakeRepository()
    service = AppointmentService(repository, registry)

    reply = service.start("9199", "సెలూన్ appointment కావాలి")
    assert registry.session.step == ConversationStep.APPOINTMENT_AREA
    assert "Nearby" in reply

    result = service.process("9199", "Vuyyuru Tomorrow 4 PM")
    assert "Request ID: #9" in result
    assert repository.created["category"] == "Salon"
    assert repository.created["area"] == "Vuyyuru"
    assert repository.created["preferred_date"] == "Tomorrow"
    assert repository.created["preferred_time"] == "4 PM"
    assert registry.session.step == ConversationStep.MAIN_MENU


def test_nearby_target_is_preserved_for_location_matching():
    registry = FakeRegistry()
    repository = FakeRepository()
    service = AppointmentService(repository, registry)

    service.start("9199", "salon appointment కావాలి")
    result = service.process("9199", "Nearby Tomorrow 6 PM")

    assert "Appointment request save" in result
    assert repository.created["area"] == "Nearby"
