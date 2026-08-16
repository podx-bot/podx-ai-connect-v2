from app.repositories.street_vendor_repository import StreetVendorRepository
from app.services.street_vendor_proximity_service import StreetVendorProximityService


class FakeDemands:
    def __init__(self, rows): self.rows = rows
    def list_active(self, limit=500, exclude_user_id=None):
        return [row for row in self.rows if str(row.get('user_id')) != str(exclude_user_id)]


class FakeUsers:
    def __init__(self, rows): self.rows = rows
    def find_by_whatsapp_mobile(self, mobile): return self.rows.get(str(mobile))


class FakeWhatsApp:
    def __init__(self, fail=False): self.sent=[]; self.fail=fail
    def send_text_message(self, recipient_mobile, message):
        if self.fail: raise RuntimeError('send failed')
        self.sent.append((recipient_mobile, message)); return {'success': True}


def _service(tmp_path, demands, users=None, whatsapp=None):
    return StreetVendorProximityService(
        StreetVendorRepository(str(tmp_path/'vendor.db')),
        FakeDemands(demands), FakeUsers(users or {}), whatsapp or FakeWhatsApp(),
        radius_km=1.5, repeat_after_hours=2, meaningful_move_km=.5,
    )


def test_vendor_on_and_nearby_matching_buyer_gets_alert(tmp_path):
    wa=FakeWhatsApp()
    demand={'id':1,'user_id':'buyer','side':'NEED','domain':'PRODUCT','subject':'tomatoes','latitude':16.51,'longitude':80.63}
    svc=_service(tmp_path,[demand],whatsapp=wa)
    assert 'Mobile vendor mode ON' in svc.process_text('vendor','VENDOR ON tomatoes, onions')
    reply=svc.process_text('vendor','VENDOR HERE 16.5105,80.6305')
    assert '1 మందికి' in reply
    assert len(wa.sent)==1 and wa.sent[0][0]=='buyer'
    assert 'tomatoes' in wa.sent[0][1]


def test_far_or_unrelated_buyer_is_not_alerted(tmp_path):
    wa=FakeWhatsApp()
    demands=[
        {'id':1,'user_id':'far','side':'NEED','domain':'PRODUCT','subject':'tomatoes','latitude':16.60,'longitude':80.70},
        {'id':2,'user_id':'near','side':'NEED','domain':'PRODUCT','subject':'milk','latitude':16.51,'longitude':80.63},
        {'id':3,'user_id':'job','side':'NEED','domain':'JOB','subject':'tomatoes','latitude':16.51,'longitude':80.63},
    ]
    svc=_service(tmp_path,demands,whatsapp=wa)
    svc.process_text('vendor','VENDOR ON tomatoes')
    reply=svc.process_text('vendor','VENDOR HERE 16.5105,80.6305')
    assert 'matching customer demand లేదు' in reply
    assert wa.sent==[]


def test_saved_user_location_is_used_when_demand_has_no_coordinates(tmp_path):
    wa=FakeWhatsApp()
    demand={'id':5,'user_id':'buyer','side':'NEED','domain':'PRODUCT','subject':'fruits','latitude':None,'longitude':None}
    users={'buyer':{'latitude':16.5102,'longitude':80.6302}}
    svc=_service(tmp_path,[demand],users=users,whatsapp=wa)
    svc.process_text('vendor','VENDOR ON fruits')
    svc.handle_location('vendor',16.5105,80.6305)
    assert len(wa.sent)==1


def test_duplicate_same_place_alert_is_suppressed(tmp_path):
    wa=FakeWhatsApp()
    demand={'id':7,'user_id':'buyer','side':'NEED','domain':'PRODUCT','subject':'vegetables','latitude':16.51,'longitude':80.63}
    svc=_service(tmp_path,[demand],whatsapp=wa)
    svc.process_text('vendor','VENDOR ON fresh vegetables')
    svc.handle_location('vendor',16.5105,80.6305)
    svc.handle_location('vendor',16.5106,80.6306)
    assert len(wa.sent)==1


def test_meaningful_vendor_move_can_generate_fresh_alert(tmp_path):
    wa=FakeWhatsApp()
    demand={'id':8,'user_id':'buyer','side':'NEED','domain':'PRODUCT','subject':'vegetables','latitude':16.515,'longitude':80.635}
    svc=_service(tmp_path,[demand],whatsapp=wa)
    svc.process_text('vendor','VENDOR ON vegetables')
    svc.handle_location('vendor',16.5100,80.6300)
    svc.handle_location('vendor',16.5150,80.6350)
    assert len(wa.sent)==2


def test_failed_delivery_does_not_create_dedupe_claim(tmp_path):
    demand={'id':9,'user_id':'buyer','side':'NEED','domain':'PRODUCT','subject':'fruits','latitude':16.51,'longitude':80.63}
    failing=FakeWhatsApp(fail=True)
    svc=_service(tmp_path,[demand],whatsapp=failing)
    svc.process_text('vendor','VENDOR ON fruits')
    svc.handle_location('vendor',16.5105,80.6305)
    assert svc.repository.alert_record('vendor','buyer',9) is None


def test_vendor_off_stops_location_updates(tmp_path):
    svc=_service(tmp_path,[])
    svc.process_text('vendor','VENDOR ON fruits')
    assert 'off' in svc.process_text('vendor','VENDOR OFF').lower()
    assert 'ముందుగా' in svc.handle_location('vendor',16.5,80.6)
