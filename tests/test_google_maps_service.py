from app.services.google_maps_service import GoogleMapsService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeClient:
    def __init__(self):
        self.get_calls = []
        self.post_calls = []
    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return FakeResponse({
            'status': 'OK',
            'results': [{
                'formatted_address': 'Vijayawada, Andhra Pradesh, India',
                'place_id': 'place-1',
                'geometry': {'location': {'lat': 16.5062, 'lng': 80.6480}},
            }],
        })
    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return FakeResponse({
            'routes': [{
                'distanceMeters': 275000,
                'duration': '16200s',
                'polyline': {'encodedPolyline': 'abc123'},
            }],
        })


def test_geocode_uses_server_side_api_key_and_returns_coordinates():
    client = FakeClient()
    maps = GoogleMapsService('secret-key', client=client)
    result = maps.geocode('Vijayawada')
    assert result['latitude'] == 16.5062
    assert result['longitude'] == 80.648
    assert client.get_calls[0][1]['params']['key'] == 'secret-key'
    assert client.get_calls[0][1]['params']['region'] == 'in'


def test_compute_route_uses_field_mask_and_intermediates():
    client = FakeClient()
    maps = GoogleMapsService('secret-key', client=client)
    result = maps.compute_route([
        {'latitude': 16.50, 'longitude': 80.64},
        {'latitude': 17.14, 'longitude': 79.62},
        {'latitude': 17.38, 'longitude': 78.48},
    ])
    assert result['distance_km'] == 275.0
    assert result['duration_minutes'] == 270
    assert result['encoded_polyline'] == 'abc123'
    _, call = client.post_calls[0]
    assert call['headers']['X-Goog-Api-Key'] == 'secret-key'
    assert 'routes.distanceMeters' in call['headers']['X-Goog-FieldMask']
    assert len(call['json']['intermediates']) == 1


def test_maps_disabled_fails_open_without_network_call():
    client = FakeClient()
    maps = GoogleMapsService('', client=client)
    assert maps.geocode('Vijayawada') is None
    assert maps.compute_route([{'latitude': 1, 'longitude': 2}, {'latitude': 3, 'longitude': 4}]) is None
    assert client.get_calls == []
    assert client.post_calls == []


def test_directions_url_supports_waypoints_without_api_key():
    url = GoogleMapsService.directions_url('Vijayawada', 'Hyderabad', ['Suryapet'])
    assert 'google.com/maps/dir/' in url
    assert 'origin=Vijayawada' in url
    assert 'destination=Hyderabad' in url
    assert 'waypoints=Suryapet' in url
