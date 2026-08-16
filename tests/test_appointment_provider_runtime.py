from app.database.database import Database
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.services.appointment_provider_runtime_service import AppointmentProviderRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, text):
        self.sent.append((str(mobile), str(text)))
        return {"success": True}


class FakeUsers:
    def __init__(self):
        self.rows = {
            "buyer": {"whatsapp_mobile": "buyer", "name": "Buyer"},
            "doc1": {"whatsapp_mobile": "doc1", "name": "Dr One"},
            "doc2": {"whatsapp_mobile": "doc2", "name": "Dr Two"},
        }

    def find_by_whatsapp_mobile(self, mobile):
        return self.rows.get(str(mobile))


def build(tmp_path):
    database = Database(str(tmp_path / "appointments.db"))
    database.create_tables()
    appointments = AppointmentRepository(database)
    marketplace = MarketplaceRepository(database)
    whatsapp = FakeWhatsApp()
    users = FakeUsers()
    runtime = AppointmentProviderRuntimeService(appointments, marketplace, whatsapp, users)
    return database, appointments, marketplace, whatsapp, runtime


def test_notifies_only_matching_area_provider(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    marketplace.save_service_provider_profile(
        provider_mobile="doc1", service_name="Doctor", details="General physician",
        area="Vuyyuru", source_message="doctor service",
    )
    marketplace.save_service_provider_profile(
        provider_mobile="doc2", service_name="Doctor", details="General physician",
        area="Vijayawada", source_message="doctor service",
    )
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Tomorrow", "4 PM")
    result = runtime.notify_matching_providers(request)
    assert result["sent"] == 1
    assert whatsapp.sent[0][0] == "doc1"
    assert f"APPT ACCEPT {request['id']}" in whatsapp.sent[0][1]
    database.close()


def test_first_accept_wins_and_customer_is_notified(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    for mobile in ("doc1", "doc2"):
        marketplace.save_service_provider_profile(
            provider_mobile=mobile, service_name="Doctor", details=None,
            area="Vuyyuru", source_message="doctor service",
        )
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Tomorrow", "4 PM")
    reply1 = runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    reply2 = runtime.process_provider_command("doc2", f"APPT ACCEPT {request['id']}")
    assert "assign" in reply1.lower()
    assert "మరో provider" in reply2
    assignment = appointments.get_assignment(request["id"])
    assert assignment["provider_mobile"] == "doc1"
    assert any(mobile == "buyer" and "appointment confirm" in text.casefold() for mobile, text in whatsapp.sent)
    database.close()


def test_assigned_provider_can_complete_appointment(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    marketplace.save_service_provider_profile(
        provider_mobile="doc1", service_name="Doctor", details=None,
        area="Vuyyuru", source_message="doctor service",
    )
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "6 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    done = runtime.process_provider_command("doc1", f"APPT DONE {request['id']}")
    assert "completed" in done.lower()
    assert appointments.get_request(request["id"])["status"] == "COMPLETED"
    assert appointments.get_assignment(request["id"])["status"] == "COMPLETED"
    database.close()


def test_non_matching_provider_cannot_claim(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    marketplace.save_service_provider_profile(
        provider_mobile="doc2", service_name="Salon", details=None,
        area="Vuyyuru", source_message="salon service",
    )
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "5 PM")
    reply = runtime.process_provider_command("doc2", f"APPT ACCEPT {request['id']}")
    assert "match" in reply.lower()
    assert appointments.get_assignment(request["id"]) is None
    database.close()
