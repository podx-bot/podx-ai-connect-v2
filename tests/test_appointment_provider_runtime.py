from app.database.database import Database
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.services.appointment_provider_runtime_service import AppointmentProviderRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile=None, text=None, **kwargs):
        recipient = kwargs.get("recipient_mobile", mobile)
        message = kwargs.get("message", text)
        self.sent.append((str(recipient), str(message)))
        return {"success": True}


class FakeUsers:
    def __init__(self):
        self.rows = {
            "buyer": {"whatsapp_mobile": "buyer", "entered_mobile": "9000000001", "name": "Buyer"},
            "doc1": {"whatsapp_mobile": "doc1", "entered_mobile": "9000000002", "name": "Dr One"},
            "doc2": {"whatsapp_mobile": "doc2", "entered_mobile": "9000000003", "name": "Dr Two"},
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


def add_doctor(marketplace, mobile="doc1", area="Vuyyuru"):
    marketplace.save_service_provider_profile(
        provider_mobile=mobile, service_name="Doctor", details="General physician",
        area=area, source_message="doctor service",
    )


def test_notifies_only_matching_area_provider(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace, "doc1", "Vuyyuru")
    add_doctor(marketplace, "doc2", "Vijayawada")
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Tomorrow", "4 PM")
    result = runtime.notify_matching_providers(request)
    assert result["sent"] == 1
    assert whatsapp.sent[0][0] == "doc1"
    assert f"APPT ACCEPT {request['id']}" in whatsapp.sent[0][1]
    database.close()


def test_first_accept_wins_but_contact_waits_for_customer_confirmation(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace, "doc1")
    add_doctor(marketplace, "doc2")
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Tomorrow", "4 PM")
    reply1 = runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    reply2 = runtime.process_provider_command("doc2", f"APPT ACCEPT {request['id']}")
    assert "accept" in reply1.lower()
    assert "మరో provider" in reply2
    assert appointments.get_request(request["id"])["status"] == "PROVIDER_ACCEPTED"
    assert appointments.get_assignment(request["id"])["provider_mobile"] == "doc1"
    combined = "\n".join(text for _, text in whatsapp.sent)
    assert "9000000001" not in combined
    assert "9000000002" not in combined
    assert f"APPT CONFIRM {request['id']}" in combined
    database.close()


def test_customer_confirm_exchanges_contacts_then_provider_can_complete(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "6 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")

    premature = runtime.process_provider_command("doc1", f"APPT DONE {request['id']}")
    assert "final confirmed" in premature.lower()

    confirm = runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")
    assert "final confirmed" in confirm.lower()
    assert "9000000002" in confirm
    assert appointments.get_request(request["id"])["status"] == "CONFIRMED"
    assert any(mobile == "doc1" and "9000000001" in text for mobile, text in whatsapp.sent)

    done = runtime.process_provider_command("doc1", f"APPT DONE {request['id']}")
    assert "completed" in done.lower()
    assert appointments.get_request(request["id"])["status"] == "COMPLETED"
    assert appointments.get_assignment(request["id"])["status"] == "COMPLETED"
    database.close()


def test_customer_confirm_is_idempotent_without_duplicate_provider_notification(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "6 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")
    count_after_first = len([x for x in whatsapp.sent if x[0] == "doc1" and "Customer contact" in x[1]])
    runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")
    count_after_second = len([x for x in whatsapp.sent if x[0] == "doc1" and "Customer contact" in x[1]])
    assert count_after_first == 1
    assert count_after_second == 1
    database.close()


def test_customer_can_cancel_latest_naturally_and_provider_is_notified_once(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Tomorrow", "4 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")
    reply = runtime.process_provider_command("buyer", "cancel appointment")
    assert "cancelled" in reply.lower()
    assert appointments.get_request(request["id"])["status"] == "CANCELLED"
    notices = len([x for x in whatsapp.sent if x[0] == "doc1" and "cancel" in x[1].casefold()])
    runtime.process_provider_command("buyer", f"APPT CANCEL {request['id']}")
    assert len([x for x in whatsapp.sent if x[0] == "doc1" and "cancel" in x[1].casefold()]) == notices
    database.close()


def test_reschedule_accept_changes_schedule_and_stays_confirmed(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "4 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")

    reply = runtime.process_provider_command("buyer", "reschedule tomorrow 6 PM")
    assert "reschedule" in reply.lower()
    assert appointments.get_request(request["id"])["status"] == "RESCHEDULE_REQUESTED"
    assert any("APPT RESCHEDULE ACCEPT" in text for mobile, text in whatsapp.sent if mobile == "doc1")

    provider_reply = runtime.process_provider_command("doc1", f"APPT RESCHEDULE ACCEPT {request['id']}")
    assert "confirmed" in provider_reply.lower()
    refreshed = appointments.get_request(request["id"])
    assert refreshed["status"] == "CONFIRMED"
    assert refreshed["preferred_date"] == "Tomorrow"
    assert refreshed["preferred_time"] == "6 PM"
    database.close()


def test_reschedule_decline_restores_old_schedule(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "4 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    runtime.process_provider_command("buyer", f"APPT CONFIRM {request['id']}")
    runtime.process_provider_command("buyer", "reschedule tomorrow 6 PM")
    runtime.process_provider_command("doc1", f"APPT RESCHEDULE DECLINE {request['id']}")
    refreshed = appointments.get_request(request["id"])
    assert refreshed["status"] == "CONFIRMED"
    assert refreshed["preferred_date"] == "Today"
    assert refreshed["preferred_time"] == "4 PM"
    database.close()


def test_status_summary_is_permission_safe(tmp_path):
    database, appointments, marketplace, whatsapp, runtime = build(tmp_path)
    add_doctor(marketplace)
    request = appointments.create_request("buyer", "Doctor", "Vuyyuru", "Today", "4 PM")
    runtime.process_provider_command("doc1", f"APPT ACCEPT {request['id']}")
    assert "PROVIDER_ACCEPTED" in runtime.process_provider_command("buyer", "appointment status")
    assert "permission" in runtime.process_provider_command("doc2", f"APPT STATUS {request['id']}").lower()
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
