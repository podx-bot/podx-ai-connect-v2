from pathlib import Path

from app.repositories.street_vendor_repository import StreetVendorRepository
from app.services.street_vendor_proximity_service import StreetVendorProximityService


class FakeDemands:
    def list_active(self, limit=500, exclude_user_id=None): return []


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile): return None


class FakeWhatsApp:
    def send_text_message(self, recipient_mobile, message): return {'success': True}


def test_shared_location_ignored_for_non_vendor(tmp_path):
    service=StreetVendorProximityService(
        StreetVendorRepository(str(tmp_path/'vendor.db')), FakeDemands(), FakeUsers(), FakeWhatsApp()
    )
    assert service.handle_shared_location('user',16.5,80.6) is None


def test_shared_location_updates_active_vendor(tmp_path):
    repo=StreetVendorRepository(str(tmp_path/'vendor.db'))
    service=StreetVendorProximityService(repo,FakeDemands(),FakeUsers(),FakeWhatsApp())
    service.process_text('vendor','VENDOR ON fruits')
    reply=service.handle_shared_location('vendor',16.5,80.6)
    assert reply is not None and 'Vendor location updated' in reply
    profile=repo.get('vendor')
    assert float(profile['latitude'])==16.5
    assert float(profile['longitude'])==80.6


def test_location_middleware_contains_vendor_third_priority_bridge():
    source=Path('app/api/appointment_location_middleware.py').read_text(encoding='utf-8')
    appointment=source.index('self.service.handle(incoming)')
    universal=source.index('universal_live_capture_service.handle_location')
    vendor=source.index('handle_shared_location')
    assert appointment < universal < vendor
    assert 'flow_name = "street_vendor"' in source
