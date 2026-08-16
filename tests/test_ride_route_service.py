from app.repositories.ride_repository import RideRepository
from app.services.ride_route_service import RideRouteService


class FakeUsers:
    def __init__(self, rows=None):
        self.rows=rows or {}
    def find_by_whatsapp_mobile(self, mobile):
        return self.rows.get(str(mobile))


def test_subroute_sequence_matches_only_forward_direction(tmp_path):
    repo=RideRepository(str(tmp_path/'ride_route.db'))
    ride_id=repo.create_ride('driver','Vijayawada','Hyderabad','2026-08-20','08:00',3,500)
    routes=RideRouteService(repo,FakeUsers())
    saved=routes.set_stops(ride_id,'driver',['Gollapudi','Suryapet'])
    assert saved['status']=='SAVED'
    assert [p['name'] for p in saved['points']]==['Vijayawada','Gollapudi','Suryapet','Hyderabad']
    forward=routes.find_subroute('p1','Gollapudi','Suryapet','2026-08-20')
    assert len(forward)==1
    assert forward[0]['pickup_name']=='Gollapudi'
    assert forward[0]['drop_name']=='Suryapet'
    reverse=routes.find_subroute('p1','Suryapet','Gollapudi','2026-08-20')
    assert reverse==[]


def test_nearest_coordinate_pickup_is_ranked_from_saved_location(tmp_path):
    repo=RideRepository(str(tmp_path/'ride_geo.db'))
    ride_id=repo.create_ride('driver','Vijayawada','Hyderabad','2026-08-20','08:00',3,None)
    users=FakeUsers({'passenger':{'latitude':16.5100,'longitude':80.6400}})
    routes=RideRouteService(repo,users)
    routes.set_stops(ride_id,'driver',['Gollapudi@16.5410,80.6030','Suryapet@17.1400,79.6200'])
    matches=routes.find_subroute('passenger','Gollapudi','Suryapet','2026-08-20')
    assert len(matches)==1
    assert matches[0]['pickup_distance_km'] is not None
    assert matches[0]['pickup_distance_km'] < 10


def test_only_driver_can_change_route_stops(tmp_path):
    repo=RideRepository(str(tmp_path/'ride_auth.db'))
    ride_id=repo.create_ride('driver','A','D','2026-08-20','08:00',2,None)
    routes=RideRouteService(repo,FakeUsers())
    assert routes.set_stops(ride_id,'other',['B','C'])['status']=='NOT_DRIVER'


def test_search_context_tracks_recommended_segment(tmp_path):
    repo=RideRepository(str(tmp_path/'ride_context.db'))
    ride_id=repo.create_ride('driver','A','D','2026-08-20','08:00',2,None)
    routes=RideRouteService(repo,FakeUsers())
    routes.set_stops(ride_id,'driver',['B','C'])
    matches=routes.find_subroute('passenger','B','D','2026-08-20')
    assert matches
    context=routes.context_for_booking('passenger',ride_id)
    assert context['pickup_name']=='B'
    assert context['drop_name']=='D'
