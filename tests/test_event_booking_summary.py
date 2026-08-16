from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.event_booking_service import EventBookingService
from app.services.event_master_rfq_service import EventMasterRFQService
from app.services.universal_rfq_service import UniversalRFQService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, body):
        self.sent.append((str(mobile), str(body)))
        return {"ok": True}


def _select(repo, service, rfq_id, provider, total, buyer='buyer'):
    quote_id = repo.start_quote(rfq_id, provider, provider_total=total)
    for item in repo.list_items(rfq_id):
        repo.set_item_quote(quote_id, item['id'], available=True, included=True)
    repo.submit_quote(quote_id)
    result = service.select_quote(rfq_id, quote_id, buyer)
    assert result['status'] == 'SELECTED'
    return quote_id


def test_event_booking_requires_all_services(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'event-book.db'))
    master_service = EventMasterRFQService(repo)
    rfq_service = UniversalRFQService(repo)
    event = master_service.create_master_event('buyer', 'Marriage', 300, 'Vijayawada', ['catering', 'decoration'], '2026-12-10')
    catering = next(x for x in event['children'] if x['service'] == 'CATERING')
    _select(repo, rfq_service, catering['rfq_id'], 'caterer1', 60000)
    booking = EventBookingService(repo, FakeWhatsApp(), lambda uid: {'mobile': uid})
    summary = booking.package_summary(event['master_rfq_id'], 'buyer')
    assert summary['combined_total'] == 60000
    assert summary['missing'] == ['DECORATION']
    assert summary['ready_to_book'] is False
    result = booking.confirm_booking(event['master_rfq_id'], 'buyer')
    assert result['status'] == 'INCOMPLETE_SELECTION'


def test_event_booking_combines_and_confirms_selected_providers(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'event-book2.db'))
    master_service = EventMasterRFQService(repo)
    rfq_service = UniversalRFQService(repo)
    event = master_service.create_master_event('buyer', 'Birthday', 100, 'Vuyyuru', ['catering', 'decoration'], '2026-09-01')
    catering = next(x for x in event['children'] if x['service'] == 'CATERING')
    decoration = next(x for x in event['children'] if x['service'] == 'DECORATION')
    _select(repo, rfq_service, catering['rfq_id'], 'caterer1', 25000)
    _select(repo, rfq_service, decoration['rfq_id'], 'decor1', 15000)
    whatsapp = FakeWhatsApp()
    booking = EventBookingService(repo, whatsapp, lambda uid: {'mobile': uid})
    summary = booking.package_summary(event['master_rfq_id'], 'buyer')
    assert summary['ready_to_book'] is True
    assert summary['combined_total'] == 40000
    result = booking.confirm_booking(event['master_rfq_id'], 'buyer')
    assert result['status'] == 'BOOKED'
    assert repo.get_rfq(event['master_rfq_id'])['status'] == 'BOOKED'
    assert repo.get_rfq(catering['rfq_id'])['status'] == 'BOOKED'
    assert repo.get_rfq(decoration['rfq_id'])['status'] == 'BOOKED'
    assert {mobile for mobile, _ in whatsapp.sent} == {'caterer1', 'decor1'}
    again = booking.confirm_booking(event['master_rfq_id'], 'buyer')
    assert again['status'] == 'ALREADY_BOOKED'
    assert len(whatsapp.sent) == 2
