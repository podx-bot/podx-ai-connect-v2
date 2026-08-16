from types import SimpleNamespace

from app.services.event_intent_extractor import EventIntentExtractor
from app.services.event_master_runtime_service import EventMasterRuntimeService


class FakeInteractions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def create(self, **kwargs):
        value = self.outputs[self.calls]
        self.calls += 1
        return SimpleNamespace(output_text=value)


class FakeClient:
    def __init__(self, outputs):
        self.interactions = FakeInteractions(outputs)


class FakeSessions:
    def __init__(self):
        self.items = {}
        self.saves = 0

    def get(self, sender):
        return self.items.setdefault(sender, SimpleNamespace(data={}))

    def save(self, sender):
        self.saves += 1


class FakeEvents:
    def __init__(self):
        self.created = []

    def create_master_event(self, **kwargs):
        self.created.append(kwargs)
        return {"status": "CREATED", "master_rfq_id": 77, "children": [{"service": "CATERING", "rfq_id": 78}]}


class RegisteredUsers:
    def find_by_whatsapp_mobile(self, sender):
        return {"registration_complete": 1}


def test_short_followup_resumes_saved_event_and_creates_rfq():
    first = '''{"is_event_request":true,"event_type":"Marriage","guest_count":null,"location_text":"Vijayawada","event_date":null,"services":["CATERING"],"confidence":0.95}'''
    second = '''{"is_event_request":true,"event_type":"Marriage","guest_count":500,"location_text":"Vijayawada","event_date":null,"services":["CATERING"],"confidence":0.98}'''
    client = FakeClient([first, second])
    extractor = EventIntentExtractor(client=client)
    sessions = FakeSessions()
    events = FakeEvents()
    runtime = EventMasterRuntimeService(events, user_repository=RegisteredUsers(), intent_extractor=extractor, session_registry=sessions)

    reply1 = runtime.process("9000", "Vijayawada marriage function catering కావాలి")
    assert "guests" in reply1
    assert sessions.get("9000").data["event_intake"]["location_text"] == "Vijayawada"
    assert not events.created

    reply2 = runtime.process("9000", "500 guests")
    assert "Event Master RFQ #77" in reply2
    assert events.created[0]["guest_count"] == 500
    assert events.created[0]["location_text"] == "Vijayawada"
    assert "event_intake" not in sessions.get("9000").data
    assert client.interactions.calls == 2


def test_followup_extractor_bypasses_event_keyword_gate_with_saved_context():
    output = '''{"is_event_request":true,"event_type":"Birthday","guest_count":100,"location_text":"Vuyyuru","event_date":null,"services":["HALL"],"confidence":0.96}'''
    client = FakeClient([output])
    extractor = EventIntentExtractor(client=client)
    result = extractor.extract_followup({"event_type":"Birthday","guest_count":null,"location_text":"Vuyyuru","services":["HALL"]}, "100")
    assert result["guest_count"] == 100
    assert result["missing"] == []
    assert client.interactions.calls == 1


def test_unrelated_message_still_bypasses_event_runtime_without_pending_state():
    client = FakeClient([])
    runtime = EventMasterRuntimeService(FakeEvents(), intent_extractor=EventIntentExtractor(client=client), session_registry=FakeSessions())
    assert runtime.process("9000", "5 kg rice కావాలి") is None
    assert client.interactions.calls == 0
