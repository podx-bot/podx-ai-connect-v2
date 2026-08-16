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


def test_accepted_booking_gets_free_unlock_entitlement(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    unlock=repo.get_unlock(1)
    assert unlock['amount']==0
    assert unlock['payment_status']=='FREE'
    passenger_messages=[text for mobile,text in wa.sent if mobile=='passenger']
    assert any('Contact unlock ready' in text for text in passenger_messages)
    assert all('₹50' not in text and 'Payment authorization' not in text for text in passenger_messages)


def test_passenger_unlocks_contacts_without_payment(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    reply=runtime.process('passenger','RIDE UNLOCK 1')
    assert 'Driver One' in reply and '9000000001' in reply
    assert repo.get_unlock(1)['payment_status']=='FREE'
    assert repo.get_unlock(1)['unlocked_at'] is not None
    driver_messages=[text for mobile,text in wa.sent if mobile=='driver']
    assert any('Passenger One' in text and '9000000002' in text for text in driver_messages)


def test_only_booking_passenger_can_unlock(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    reply=runtime.process('other','RIDE UNLOCK 1')
    assert 'passengerకి మాత్రమే' in reply
    assert '9000000001' not in reply


def test_legacy_admin_payment_hook_stays_non_charging(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    reply=runtime.process('admin','RIDE PAYMENT OK 1 | old-callback')
    assert 'Payment gateway is disabled' in reply
    unlock=repo.get_unlock(1)
    assert unlock['amount']==0
    assert unlock['payment_status']=='FREE'


def test_legacy_pending_unlock_is_migrated_to_free(tmp_path):
    db_path=str(tmp_path/'legacy_unlock.db')
    repo=RideRepository(db_path)
    repo.create_ride('driver','Vijayawada','Hyderabad','2026-08-20','7 AM',2,900)
    repo.create_booking(1,'passenger',1)
    repo.decide_booking(1,'driver',True)
    with repo._connect() as conn:
        conn.execute("UPDATE ride_contact_unlocks SET amount=50,payment_status='PENDING',payment_ref=NULL,authorized_at=NULL WHERE booking_id=1")
    migrated=RideRepository(db_path).get_unlock(1)
    assert migrated['amount']==0
    assert migrated['payment_status']=='FREE'
    assert migrated['authorized_at'] is not None


def test_driver_completes_booking_idempotently(tmp_path):
    repo,wa,runtime=setup_accepted(tmp_path)
    first=runtime.process('driver','RIDE DONE 1')
    second=runtime.process('driver','RIDE DONE 1')
    assert 'completedగా' in first
    assert 'ఇప్పటికే completed' in second
    assert repo.get_booking(1)['status']=='COMPLETED'
    passenger_done=[text for mobile,text in wa.sent if mobile=='passenger' and 'completed' in text.casefold()]
    assert len(passenger_done)==1
