from app.repositories.ride_repository import RideRepository
from app.services.ride_natural_intake_service import RideNaturalIntakeService
from app.services.ride_runtime_service import RideRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, text):
        self.sent.append((mobile, text))
        return {"ok": True}


def test_telugu_driver_message_continues_with_only_missing_time(tmp_path):
    db = str(tmp_path / "ride.db")
    repo = RideRepository(db)
    runtime = RideRuntimeService(repo, FakeWhatsApp())

    first = runtime.process("driver1", "రేపు విజయవాడ నుంచి హైదరాబాద్ వెళ్తున్నాను, 3 seats ఉన్నాయి")
    assert "సమయానికి" in first

    second = runtime.process("driver1", "ఉదయం 8")
    assert "Ride #" in second
    ride = repo.get_ride(1)
    assert ride["origin"] == "విజయవాడ"
    assert ride["destination"] == "హైదరాబాద్"
    assert ride["travel_date"] == "Tomorrow"
    assert ride["travel_time"] == "8 AM"
    assert ride["seats_available"] == 3


def test_english_passenger_natural_message_finds_existing_ride(tmp_path):
    db = str(tmp_path / "ride.db")
    repo = RideRepository(db)
    repo.create_ride("driver1", "Vijayawada", "Hyderabad", "Tomorrow", "8 AM", 3, 500)
    runtime = RideRuntimeService(repo, FakeWhatsApp())

    reply = runtime.process("passenger1", "I need a ride tomorrow from Vijayawada to Hyderabad")
    assert "Available PODX rides" in reply
    assert "Vijayawada → Hyderabad" in reply
    assert "₹500/seat" in reply


def test_unrelated_message_is_not_captured_as_ride(tmp_path):
    service = RideNaturalIntakeService(str(tmp_path / "ride.db"))
    assert service.process("u1", "Chicken price ఎంత?") is None
    assert service.process("u1", "నాకు electrician కావాలి") is None


def test_pending_ride_intake_survives_service_restart(tmp_path):
    db = str(tmp_path / "ride.db")
    first = RideNaturalIntakeService(db)
    reply = first.process("u1", "Tomorrow I am driving from Vijayawada to Hyderabad with 2 seats available")
    assert reply["reply"]
    assert "సమయానికి" in reply["reply"]

    second = RideNaturalIntakeService(db)
    completed = second.process("u1", "7:30 AM")
    assert completed["action"] == "POST"
    assert completed["origin"] == "Vijayawada"
    assert completed["destination"] == "Hyderabad"
    assert completed["travel_date"] == "Tomorrow"
    assert completed["travel_time"] == "7:30 AM"
    assert completed["seats"] == 2


def test_telugu_passenger_route_can_be_completed_in_one_message(tmp_path):
    service = RideNaturalIntakeService(str(tmp_path / "ride.db"))
    result = service.process("u1", "రేపు విజయవాడ నుంచి హైదరాబాద్ ride కావాలి")
    assert result["action"] == "FIND"
    assert result["origin"] == "విజయవాడ"
    assert result["destination"] == "హైదరాబాద్"
    assert result["travel_date"] == "Tomorrow"
