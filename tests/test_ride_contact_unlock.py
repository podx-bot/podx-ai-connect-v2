from app.repositories.ride_repository import RideRepository
from app.services.ride_runtime_service import RideRuntimeService


class FakeWhatsApp:
    def __init__(self): self.sent=[]
    def send_text_message(self,mobile,text): self.sent.append((str(mobile),str(text))); return {"success":True}

class FakeUsers:
    def __init__(self):
        self.rows={
            'driver':{'whatsapp_mobile':'driver','entered_mobile':'9000000001','name':'Driver One'},
            'passenger':{'whatsapp_mobile':'passenger','entered_mobile':'9000000002','name':'Passenger One'},
            'admin':{'whatsapp_mobile':'admin','entered_mobile':'9000000003','name':'Admin'},
        }
    def find_by_whatsapp_mobile(self,mobile): return self.rows.get(str(mobile))


def setup_accepted(tmp_path):
    repo=RideRepository(str(tmp_path/'ride_unlock.db')); wa=FakeWhatsApp(); users=FakeUsers(); runtime=RideRuntimeService(repo,wa,users,admin_mobile='admin')
    runtime.process('driver','RIDE POST Vijayawada | Hyderabad | 2026-08-20 | 7 AM | 2 | 900')
    runtime.process('passenger','RIDE BOOK 1')
    runtime.process('driver','RIDE ACCEPT 1')
    return repo,wa,runtime


def test_unpaid_unlock_does_not_expose_driver_contact(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    reply=runtime.process('passenger','RIDE UNLOCK 1')
    assert '₹50' in reply and 'authorized' in reply
    assert '9000000001' not in reply
    assert repo.get_unlock(1)['payment_status']=='PENDING'


def test_non_admin_cannot_authorize_payment(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    reply=runtime.process('passenger','RIDE PAYMENT OK 1 | fake-ref')
    assert 'admin/internal' in reply
    assert repo.get_unlock(1)['payment_status']=='PENDING'


def test_admin_authorize_then_passenger_unlocks_contacts(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    admin=runtime.process('admin','RIDE PAYMENT OK 1 | pay_123')
    assert 'authorized' in admin
    reply=runtime.process('passenger','RIDE UNLOCK 1')
    assert 'Driver One' in reply and '9000000001' in reply
    assert repo.get_unlock(1)['payment_status']=='PAID'
    assert repo.get_unlock(1)['unlocked_at'] is not None
    driver_messages=[text for mobile,text in wa.sent if mobile=='driver']
    assert any('Passenger One' in text and '9000000002' in text for text in driver_messages)


def test_only_booking_passenger_can_unlock(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    runtime.process('admin','RIDE PAYMENT OK 1 | pay_123')
    reply=runtime.process('other','RIDE UNLOCK 1')
    assert 'passengerకి మాత్రమే' in reply
    assert '9000000001' not in reply


def test_driver_completes_booking_idempotently(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    first=runtime.process('driver','RIDE DONE 1')
    second=runtime.process('driver','RIDE DONE 1')
    assert 'completedగా' in first
    assert 'ఇప్పటికే completed' in second
    assert repo.get_booking(1)['status']=='COMPLETED'
    passenger_done=[text for mobile,text in wa.sent if mobile=='passenger' and 'completed' in text.casefold()]
    assert len(passenger_done)==1
