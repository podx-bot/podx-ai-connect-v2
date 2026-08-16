from app.services.local_mobility_runtime_service import LocalMobilityRuntimeService


class FakeDB:
    def __init__(self, riders): self.riders=riders
    def fetchall(self, *_args, **_kwargs): return self.riders


class FakeUsers:
    def __init__(self, people):
        self.people=people
        self.database=FakeDB([p for p in people.values() if p.get('is_rider')])
        self.capabilities={k:set(v.get('capabilities',[])) for k,v in people.items()}
    def find_by_whatsapp_mobile(self, mobile): return self.people.get(str(mobile))
    def has_capability(self, mobile, cap): return cap in self.capabilities.get(str(mobile),set())
    def add_capability(self, mobile, cap, source=None): self.capabilities.setdefault(str(mobile),set()).add(cap)


class FakeWhatsApp:
    def __init__(self): self.texts=[]; self.buttons=[]
    def send_text_message(self, mobile, body): self.texts.append((str(mobile),body)); return {'messages':[{'id':'m'}]}
    def send_reply_buttons(self, mobile, body, buttons): self.buttons.append((str(mobile),body,buttons)); return {'messages':[{'id':'b'}]}


def _runtime(tmp_path):
    people={
        'buyer': {'whatsapp_mobile':'buyer','entered_mobile':'9001','name':'Buyer','registration_complete':1,'latitude':16.5,'longitude':80.6},
        'rider': {'whatsapp_mobile':'rider','entered_mobile':'9002','name':'Rider','registration_complete':1,'latitude':16.51,'longitude':80.61,'is_rider':True,'capabilities':['BIKE_RIDER']},
    }
    wa=FakeWhatsApp(); users=FakeUsers(people)
    return LocalMobilityRuntimeService(str(tmp_path/'mob.db'),users,wa),wa


def test_request_waits_for_customer_confirmation(tmp_path):
    runtime,wa=_runtime(tmp_path)
    reply=runtime.process('buyer','BIKE Benz Circle | Bus Stand | 5 km')
    assert 'Estimated fare' in reply
    assert 'MOB CONFIRM' in reply
    assert wa.buttons == []
    job=runtime.jobs.get(1)
    assert job['status']=='DRAFT'
    assert job['trip_distance_km']==5.0
    assert job['fare_amount'] > 25
    confirmed=runtime.process('buyer','MOB CONFIRM 1')
    assert 'confirmed' in confirmed
    assert len(wa.buttons)==1


def test_contact_hidden_until_requester_unlocks(tmp_path):
    runtime,wa=_runtime(tmp_path)
    runtime.process('buyer','BIKE Benz Circle | Bus Stand | 4 km')
    runtime.process('buyer','MOB CONFIRM 1')
    accepted=runtime.process('rider','MOB ACCEPT 1')
    assert 'assign' in accepted
    buyer_messages='\n'.join(body for mobile,body in wa.texts if mobile=='buyer')
    assert '9002' not in buyer_messages
    unlock=runtime.process('buyer','MOB UNLOCK 1')
    assert '9002' in unlock
    rider_messages='\n'.join(body for mobile,body in wa.texts if mobile=='rider')
    assert '9001' in rider_messages


def test_non_requester_cannot_confirm_or_unlock(tmp_path):
    runtime,_=_runtime(tmp_path)
    runtime.process('buyer','PARCEL Shop | Home | 3 km')
    assert 'requester' in runtime.process('rider','MOB CONFIRM 1')
    assert 'requester' in runtime.process('rider','MOB UNLOCK 1')
