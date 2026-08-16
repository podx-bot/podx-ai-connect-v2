from app.repositories.ride_repository import RideRepository
from app.services.ride_runtime_service import RideRuntimeService


class FakeWhatsApp:
    def __init__(self):
        self.sent=[]
    def send_text_message(self,mobile,text):
        self.sent.append((mobile,text)); return {"ok":True}


def test_passenger_can_book_ride_naturally(tmp_path):
    repo=RideRepository(str(tmp_path/'ride.db')); wa=FakeWhatsApp(); runtime=RideRuntimeService(repo,wa)
    ride_id=repo.create_ride('driver1','Vijayawada','Hyderabad','Tomorrow','8 AM',3,500)
    reply=runtime.process('passenger1',f'Book ride {ride_id}, 2 seats')
    assert 'Seat request #' in reply
    booking=repo.get_booking(1)
    assert booking['seats']==2
    assert booking['status']=='REQUESTED'


def test_driver_can_accept_latest_pending_with_plain_accept(tmp_path):
    repo=RideRepository(str(tmp_path/'ride.db')); wa=FakeWhatsApp(); runtime=RideRuntimeService(repo,wa)
    ride_id=repo.create_ride('driver1','Vijayawada','Hyderabad','Tomorrow','8 AM',3,None)
    repo.create_booking(ride_id,'p1',1)
    reply=runtime.process('driver1','accept')
    assert 'accept అయింది' in reply
    assert repo.get_booking(1)['status']=='ACCEPTED'


def test_plain_accept_without_driver_pending_is_not_hijacked(tmp_path):
    repo=RideRepository(str(tmp_path/'ride.db')); runtime=RideRuntimeService(repo,FakeWhatsApp())
    assert runtime.process('someone','accept') is None


def test_latest_pending_booking_is_selected_for_driver(tmp_path):
    repo=RideRepository(str(tmp_path/'ride.db')); runtime=RideRuntimeService(repo,FakeWhatsApp())
    ride_id=repo.create_ride('driver1','A','B','Tomorrow','8 AM',3,None)
    repo.create_booking(ride_id,'p1',1)
    repo.create_booking(ride_id,'p2',1)
    runtime.process('driver1','reject')
    assert repo.get_booking(2)['status']=='REJECTED'
    assert repo.get_booking(1)['status']=='REQUESTED'


def test_other_driver_cannot_consume_pending_request(tmp_path):
    repo=RideRepository(str(tmp_path/'ride.db')); runtime=RideRuntimeService(repo,FakeWhatsApp())
    ride_id=repo.create_ride('driver1','A','B','Tomorrow','8 AM',2,None)
    repo.create_booking(ride_id,'p1',1)
    assert runtime.process('driver2','accept') is None
    assert repo.get_booking(1)['status']=='REQUESTED'
