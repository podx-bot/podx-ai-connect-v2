from types import SimpleNamespace

from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.event_intent_extractor import EventIntentExtractor
from app.services.event_master_rfq_service import EventMasterRFQService
from app.services.event_master_runtime_service import EventMasterRuntimeService


class FakeInteractions:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text):
        self.interactions = FakeInteractions(output_text)


def test_event_extractor_gates_non_event_without_ai_call():
    client = FakeClient('{}')
    extractor = EventIntentExtractor(client=client)
    assert extractor.extract('I need 5 kg rice near me') is None
    assert client.interactions.calls == 0


def test_event_extractor_understands_natural_function_request():
    client = FakeClient('''{
      "is_event_request": true,
      "event_type": "Marriage",
      "guest_count": 500,
      "location_text": "Vijayawada",
      "event_date": "2026-12-10",
      "services": ["CATERING", "HALL", "DECORATION", "PHOTOGRAPHY"],
      "confidence": 0.96
    }''')
    extractor = EventIntentExtractor(client=client)
    result = extractor.extract('500 మందికి Vijayawada లో marriage function, catering hall decoration photography కావాలి')
    assert result['event_type'] == 'Marriage'
    assert result['guest_count'] == 500
    assert result['location_text'] == 'Vijayawada'
    assert result['services'] == ['CATERING', 'HALL', 'DECORATION', 'PHOTOGRAPHY']
    assert result['missing'] == []


def test_natural_event_runtime_creates_master_and_children(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'natural-event.db'))
    event_service = EventMasterRFQService(repo)
    client = FakeClient('''{
      "is_event_request": true,
      "event_type": "Birthday",
      "guest_count": 100,
      "location_text": "Vuyyuru",
      "event_date": null,
      "services": ["CATERING", "DECORATION"],
      "confidence": 0.94
    }''')
    runtime = EventMasterRuntimeService(event_service, intent_extractor=EventIntentExtractor(client=client))
    reply = runtime.process('buyer', 'Vuyyuru lo birthday function 100 people, catering and decoration kavali')
    assert 'Event Master RFQ' in reply
    assert 'CATERING' in reply
    assert 'DECORATION' in reply


def test_natural_event_runtime_asks_only_missing_details(tmp_path):
    repo = UniversalRFQRepository(str(tmp_path / 'natural-event2.db'))
    client = FakeClient('''{
      "is_event_request": true,
      "event_type": "Marriage",
      "guest_count": null,
      "location_text": "Vijayawada",
      "event_date": null,
      "services": ["CATERING"],
      "confidence": 0.93
    }''')
    runtime = EventMasterRuntimeService(EventMasterRFQService(repo), intent_extractor=EventIntentExtractor(client=client))
    reply = runtime.process('buyer', 'Vijayawada marriage function catering కావాలి')
    assert 'ఎంతమంది guests?' in reply
    assert 'function location ఎక్కడ?' not in reply
    assert repo.get_rfq(1) is None
