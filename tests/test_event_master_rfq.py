from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.event_master_rfq_service import EventMasterRFQService
from app.services.event_master_runtime_service import EventMasterRuntimeService


def test_event_master_splits_services(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'event.db'))
    service = EventMasterRFQService(repo)
    result = service.create_master_event(
        'buyer', 'Marriage', 500, 'Vijayawada',
        ['catering', 'function hall', 'decoration', 'photography', 'flowers', 'sound', 'transport'],
        '2026-12-10',
    )
    assert result['status'] == 'CREATED'
    assert len(result['children']) == 7
    assert [x['service'] for x in result['children']] == [
        'CATERING', 'HALL', 'DECORATION', 'PHOTOGRAPHY', 'FLOWERS', 'SOUND', 'TRANSPORT'
    ]
    master = repo.get_rfq(result['master_rfq_id'])
    assert master['rfq_type'] == 'EVENT'
    assert master['guest_count'] == 500
    assert master['event_date'] == '2026-12-10'
    for child in result['children']:
        row = repo.get_rfq(child['rfq_id'])
        assert row['rfq_type'] == child['rfq_type']
        assert row['metadata']['master_event_rfq_id'] == result['master_rfq_id']
        assert row['metadata']['service_type'] == child['service']


def test_event_runtime_returns_sub_rfqs(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'event2.db'))
    runtime = EventMasterRuntimeService(EventMasterRFQService(repo))
    reply = runtime.process(
        'buyer',
        'EVENT RFQ Birthday | 100 | Vuyyuru | catering, decoration, photography | 2026-09-01',
    )
    assert 'Event Master RFQ' in reply
    assert 'CATERING' in reply
    assert 'DECORATION' in reply
    assert 'PHOTOGRAPHY' in reply


def test_event_service_normalizes_telugu_and_dedupes():
    services = EventMasterRFQService.normalize_services([
        'కేటరింగ్', 'హాల్', 'డెకరేషన్', 'ఫోటోగ్రఫీ', 'పూలు', 'సౌండ్', 'ట్రాన్స్‌పోర్ట్', 'catering'
    ])
    assert services == ['CATERING', 'HALL', 'DECORATION', 'PHOTOGRAPHY', 'FLOWERS', 'SOUND', 'TRANSPORT']
