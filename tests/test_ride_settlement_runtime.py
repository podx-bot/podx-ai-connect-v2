from app.repositories.ride_repository import RideRepository
from app.repositories.ride_settlement_repository import RideSettlementRepository
from app.services.ride_settlement_runtime_service import RideSettlementRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []
    def send_text_message(self, mobile, text):
        self.sent.append((str(mobile), str(text)))
        return {"success": True}


class FakeUsers:
    def __init__(self):
        self.rows = {
            "driver": {"whatsapp_mobile": "driver", "name": "Driver"},
            "passenger": {"whatsapp_mobile": "passenger", "name": "Passenger"},
        }
    def find_by_whatsapp_mobile(self, mobile):
        return self.rows.get(str(mobile))


class FakeDelegate:
    def process(self, sender_user_id, message):
        if str(message).upper().startswith("RIDE DONE"):
            return "✅ Booking #1 completedగా mark అయింది."
        return None


def setup_booking(tmp_path):
    repo = RideRepository(str(tmp_path / "settlement.db"))
    ride_id = repo.create_ride("driver", "Vijayawada", "Hyderabad", "2026-08-20", "08:00", 3, 500)
    booking_id = repo.create_booking(ride_id, "passenger", 2)["booking_id"]
    repo.decide_booking(booking_id, "driver", True)
    settlements = RideSettlementRepository(repo.db_path)
    wa = FakeWhatsApp()
    runtime = RideSettlementRuntimeService(FakeDelegate(), repo, wa, FakeUsers(), settlements)
    return repo, settlements, wa, runtime, booking_id


def test_driver_can_propose_final_fare_with_zero_platform_charge(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    reply = runtime.process("driver", f"RIDE FINAL {booking_id} | 900")
    row = settlements.get(booking_id)
    assert "₹900" in reply
    assert row["final_fare"] == 900
    assert row["platform_charge"] == 0
    assert row["status"] == "FARE_PROPOSED"
    assert any("RIDE FINAL OK" in text and "₹0" in text for mobile, text in wa.sent if mobile == "passenger")


def test_only_driver_can_propose_and_only_passenger_can_confirm(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    denied = runtime.process("passenger", f"RIDE FINAL {booking_id} | 900")
    assert "driver మాత్రమే" in denied
    runtime.process("driver", f"RIDE FINAL {booking_id} | 900")
    denied_confirm = runtime.process("driver", f"RIDE FINAL OK {booking_id}")
    assert "passengerకి మాత్రమే" in denied_confirm


def test_passenger_confirmation_records_confirmed_settlement(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    runtime.process("driver", f"RIDE FINAL {booking_id} | 950")
    reply = runtime.process("passenger", f"RIDE FINAL OK {booking_id}")
    row = settlements.get(booking_id)
    assert "confirmed" in reply
    assert row["passenger_confirmed_at"] is not None
    assert row["status"] == "FARE_CONFIRMED"
    assert row["platform_charge"] == 0


def test_done_is_non_blocking_and_marks_completion_audit(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    reply = runtime.process("driver", f"RIDE DONE {booking_id}")
    row = settlements.get(booking_id)
    assert "completed" in reply
    assert row["completed_at"] is not None
    assert row["platform_charge"] == 0
    assert row["status"] == "COMPLETED"


def test_confirm_after_completion_marks_settled(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    runtime.process("driver", f"RIDE FINAL {booking_id} | 1000")
    runtime.process("driver", f"RIDE DONE {booking_id}")
    runtime.process("passenger", f"RIDE FINAL OK {booking_id}")
    row = settlements.get(booking_id)
    assert row["status"] == "SETTLED"
    assert row["platform_charge"] == 0


def test_settlement_status_hidden_from_unrelated_user(tmp_path):
    repo, settlements, wa, runtime, booking_id = setup_booking(tmp_path)
    reply = runtime.process("other", f"RIDE SETTLEMENT {booking_id}")
    assert "passenger/driver" in reply
