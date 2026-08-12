from app.models.session import ConversationStep
from app.models.whatsapp import IncomingLocationMessage
from app.services.appointment_location_service import AppointmentLocationService


class FakeSession:
    def __init__(self):
        self.step = ConversationStep.APPOINTMENT_AREA
        self.data = {"appointment_category": "Salon"}


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
        self.location = None

    def save_location(self, **kwargs):
        self.location = kwargs


def test_shared_location_advances_appointment_to_date_time_step():
    registry = FakeRegistry()
    users = FakeUserRepository()
    service = AppointmentLocationService(users, registry)
    incoming = IncomingLocationMessage(
        provider_message_id="wamid.loc1",
        sender_mobile="9199",
        latitude=16.366,
        longitude=80.844,
        name="Vuyyuru",
        address="Krishna District",
    )

    reply = service.handle(incoming)

    assert users.location["latitude"] == 16.366
    assert registry.session.data["appointment_area"] == "Vuyyuru"
    assert registry.session.data["appointment_latitude"] == 16.366
    assert registry.session.data["appointment_longitude"] == 80.844
    assert registry.session.step == ConversationStep.APPOINTMENT_DATE
    assert "Tomorrow 4 PM" in reply
