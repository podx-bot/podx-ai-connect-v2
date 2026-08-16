from app.repositories.demand_signal_repository import DemandSignalRepository
from app.services.demand_intelligence_service import DemandIntelligenceService


class FakeDemands:
    def list_active(self, limit=500):
        return [
            {"id":1,"user_id":"b1","side":"NEED","domain":"PRODUCT","subject":"Sona Masoori Rice","location_text":"Vuyyuru","latitude":16.36,"longitude":80.84},
            {"id":2,"user_id":"b2","side":"NEED","domain":"PRODUCT","subject":"Sona Masoori Rice","location_text":"Vuyyuru","latitude":16.36,"longitude":80.84},
        ]


class FakeTargeting:
    def build_plan(self, request, already_contacted_user_ids=None, per_wave_limit=10):
        return {"waves":[{"wave":1,"targets":[{"user_id":"seller1"},{"user_id":"seller1"}]}]}


class FakeWhatsApp:
    def __init__(self): self.sent=[]
    def send_text_message(self, mobile, body):
        self.sent.append((mobile,body)); return {"success":True}


def test_recurring_demand_notifies_once_and_persists_dedupe(tmp_path):
    signals=DemandSignalRepository(str(tmp_path/'demand.db')); wa=FakeWhatsApp()
    service=DemandIntelligenceService(FakeDemands(),FakeTargeting(),signals,wa,lambda uid:{"mobile":uid},min_count=2)
    first=service.scan_and_notify(); second=service.scan_and_notify()
    assert first["status"]=="NOTIFIED"; assert first["notified"]==1
    assert "2 active customer requests" in wa.sent[0][1]
    assert second["status"]=="NO_NEW_SIGNAL"; assert len(wa.sent)==1; assert signals.count()==1


def test_below_threshold_does_not_notify(tmp_path):
    class OneDemand(FakeDemands):
        def list_active(self, limit=500): return super().list_active(limit)[:1]
    wa=FakeWhatsApp(); service=DemandIntelligenceService(OneDemand(),FakeTargeting(),DemandSignalRepository(str(tmp_path/'one.db')),wa,lambda uid:{"mobile":uid},min_count=2)
    assert service.scan_and_notify()["status"]=="NO_NEW_SIGNAL"; assert wa.sent==[]
