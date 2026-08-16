from app.repositories.ride_repository import RideRepository
from app.services.ride_runtime_service import RideRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent=[]
    def send_text_message(self,mobile,text):
        self.sent.append((str(mobile),str(text))); return {"success":True}


class FakeUsers:
    def __init__(self):
        self.rows={
            "driver":{"whatsapp_mobile":"driver","name":"Driver One"},
            "passenger":{"whatsapp_mobile":"passenger","name":"Passenger One"},
        }
    def find_by_whatsapp_mobile(self,mobile):
        return self.rows.get(str(mobile))


def build(tmp_path):
    repo=RideRepository(str(tmp_path/'rides.db')); whatsapp=FakeWhatsApp(); users=FakeUsers()
    return repo,whatsapp,RideRuntimeService(repo,whatsapp,users)


def test_post_and_find_ride(tmp_path):
    repo,whatsapp,runtime=build(tmp_path)
    post=runtime.process('driver','RIDE POST Vijayawada | Hyderabad | 2026-08-20 | 7 AM | 3 | 900')
    assert 'Ride #1' in post
    found=runtime.process('passenger','RIDE FIND Vijayawada | Hyderabad | 2026-08-20')
    assert '#1 Vijayawada → Hyderabad' in found
    assert '3 seats' in found


def test_booking_notifies_driver_and_accept_decrements_seats(tmp_path):
    repo,whatsapp,runtime=build(tmp_path)
    runtime.process('driver','RIDE POST Vijayawada | Hyderabad | 2026-08-20 | 7 AM | 3 | 900')
    booked=runtime.process('passenger','RIDE BOOK 1 2')
    assert 'Seat request #1' in booked
    assert whatsapp.sent[-1][0]=='driver'
    assert 'RIDE ACCEPT 1' in whatsapp.sent[-1][1]
    accepted=runtime.process('driver','RIDE ACCEPT 1')
    assert 'Remaining seats: 1' in accepted
    ride=repo.get_ride(1)
    assert ride['seats_available']==1
    assert any(m=='passenger' and 'accept అయింది' in t for m,t in whatsapp.sent)


def test_duplicate_accept_is_idempotent(tmp_path):
    repo,whatsapp,runtime=build(tmp_path)
    runtime.process('driver','RIDE POST A | B | 2026-08-20 | 7 AM | 2')
    runtime.process('passenger','RIDE BOOK 1')
    runtime.process('driver','RIDE ACCEPT 1')
    sent_before=len(whatsapp.sent)
    repeat=runtime.process('driver','RIDE ACCEPT 1')
    assert 'ఇప్పటికే accepted' in repeat
    assert len(whatsapp.sent)==sent_before
    assert repo.get_ride(1)['seats_available']==1


def test_driver_cannot_over_accept_remaining_seats(tmp_path):
    repo,whatsapp,runtime=build(tmp_path)
    runtime.process('driver','RIDE POST A | B | 2026-08-20 | 7 AM | 1')
    repo.create_booking(1,'passenger',1)
    first=runtime.process('driver','RIDE ACCEPT 1')
    assert 'accept అయింది' in first
    second=repo.create_booking(1,'other',1)
    assert second['status']=='RIDE_NOT_OPEN'
