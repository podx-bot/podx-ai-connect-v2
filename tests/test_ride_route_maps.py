from app.repositories.ride_repository import RideRepository
from app.services.ride_route_service import RideRouteService


class FakeMaps:
    enabled = True
    def __init__(self):
        self.lookups = []
    def geocode(self, place):
        self.lookups.append(place)
        coords = {
            'Vijayawada': (16.5062, 80.6480),
            'Suryapet': (17.1400, 79.6200),
            'Hyderabad': (17.3850, 78.4867),
        }
        if place not in coords:
            return None
        lat, lon = coords[place]
        return {'name': place, 'latitude': lat, 'longitude': lon}
    def compute_route(self, points):
        assert all(point.get('latitude') is not None for point in points)
        return {'distance_meters': 275000, 'distance_km': 275.0, 'duration_seconds': 16200, 'duration_minutes': 270, 'encoded_polyline': 'poly'}
    @staticmethod
    def directions_url(origin, destination, waypoints=None):
        middle = ','.join(waypoints or [])
        return f'maps://{origin}/{middle}/{destination}'


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile):
        return None


def test_set_stops_geocodes_missing_coordinates_and_builds_overview(tmp_path):
    repo = RideRepository(str(tmp_path / 'maps-route.db'))
    ride_id = repo.create_ride('driver', 'Vijayawada', 'Hyderabad', '2026-08-20', '08:00', 3, 500)
    maps = FakeMaps()
    routes = RideRouteService(repo, FakeUsers(), maps_service=maps)
    saved = routes.set_stops(ride_id, 'driver', ['Suryapet'])
    assert saved['status'] == 'SAVED'
    assert maps.lookups == ['Suryapet', 'Vijayawada', 'Hyderabad']
    assert all(point['latitude'] is not None for point in saved['points'])
    assert saved['overview']['distance_km'] == 275.0
    assert saved['overview']['duration_minutes'] == 270
    assert saved['overview']['directions_url'] == 'maps://Vijayawada/Suryapet/Hyderabad'


def test_subroute_match_includes_shareable_directions_link(tmp_path):
    repo = RideRepository(str(tmp_path / 'maps-match.db'))
    ride_id = repo.create_ride('driver', 'Vijayawada', 'Hyderabad', '2026-08-20', '08:00', 3, None)
    routes = RideRouteService(repo, FakeUsers(), maps_service=FakeMaps())
    routes.set_stops(ride_id, 'driver', ['Suryapet'])
    matches = routes.find_subroute('passenger', 'Suryapet', 'Hyderabad', '2026-08-20')
    assert len(matches) == 1
    assert matches[0]['directions_url'] == 'maps://Suryapet//Hyderabad'
