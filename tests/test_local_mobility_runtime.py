from app.services.local_mobility_runtime_service import LocalMobilityRuntimeService


class FakeUsers:
    def __init__(self):
        self.database = self
        self.users = {
            "buyer": {"whatsapp_mobile":"buyer","name":"Buyer","registration_complete":1,"latitude":16.50,"longitude":80.64},
            "r1": {"whatsapp_mobile":"r1","name":"Rider One","registration_complete":1,"latitude":16.51,"longitude":80.64},
            "r2": {"whatsapp_mobile":"r2","name":"Rider Two","registration_complete":1,"latitude":16.52,"longitude":80.64},
        }
        self.caps = {"r1":{"DELIVERY_PARTNER"}, "r2":{"BIKE_RIDER"}}

    def find_by_whatsapp_mobile(self, mobile):
        return self.users.get(str(mobile))

    def add_capability(self, mobile, capability, source=None):
        self.caps.setdefault(str(mobile), set()).add(str(capability))

    def has_capability(self, mobile, capability):
        return str(capability) in self.caps.get(str(mobile), set())

    def fetchall(self, sql, params=()):
        rows=[]
        for mobile, user in self.users.items():
            if self.caps.get(mobile, set()) & {"BIKE_RIDER","DELIVERY_PARTNER"}:
                rows.append(user)
        return rows


class FakeWhatsApp:
    def __init__(self): self.sent=[]
    def send_reply_buttons(self, mobile, body, buttons):
        self.sent.append(("buttons",str(mobile),body,buttons)); return {"messages":[{"id":"x"}]}
    def send_text_message(self, mobile, body):
        self.sent.append(("text",str(mobile),body)); return {"messages":[{"id":"x"}]}


def test_bike_request_offers_nearby_and_first_accept_wins(tmp_path):
    users=FakeUsers(); wa=FakeWhatsApp(); runtime=LocalMobilityRuntimeService(str(tmp_path/'m.db'),users,wa)
    reply=runtime.process("buyer","BIKE Benz Circle | Railway Station")
    assert "Bike Taxi request #1" in reply
    offered={row[1] for row in wa.sent if row[0]=="buttons"}
    assert offered=={"r1","r2"}
    assert "assign" in runtime.process("r1","MOB ACCEPT 1")
    assert "ఇప్పటికే మరో rider" in runtime.process("r2","MOB ACCEPT 1")
    assert runtime.jobs.get(1)["assigned_rider_id"]=="r1"


def test_parcel_lifecycle_notifies_requester(tmp_path):
    users=FakeUsers(); wa=FakeWhatsApp(); runtime=LocalMobilityRuntimeService(str(tmp_path/'p.db'),users,wa)
    reply=runtime.process("buyer","PARCEL Vuyyuru | Vijayawada | documents")
    assert "Parcel request #1" in reply
    assert "assign" in runtime.process("r2","MOB ACCEPT 1")
    assert "Pickup saved" in runtime.process("r2","MOB PICKUP 1")
    assert "On the way" in runtime.process("r2","MOB ONWAY 1")
    assert "completed" in runtime.process("r2","MOB DONE 1")
    assert runtime.jobs.get(1)["status"]=="COMPLETED"
    buyer_texts=[row[2] for row in wa.sent if row[0]=="text" and row[1]=="buyer"]
    assert any("pickup complete" in x for x in buyer_texts)
    assert any("completed" in x for x in buyer_texts)


def test_rider_on_reuses_delivery_partner_capability(tmp_path):
    users=FakeUsers(); users.caps["buyer"]=set(); wa=FakeWhatsApp(); runtime=LocalMobilityRuntimeService(str(tmp_path/'r.db'),users,wa)
    reply=runtime.process("buyer","RIDER ON")
    assert "Rider mode ON" in reply
    assert users.has_capability("buyer","BIKE_RIDER")
    assert users.has_capability("buyer","DELIVERY_PARTNER")


def test_natural_bike_request_is_detected(tmp_path):
    users=FakeUsers(); wa=FakeWhatsApp(); runtime=LocalMobilityRuntimeService(str(tmp_path/'n.db'),users,wa)
    reply=runtime.process("buyer","bike taxi Benz Circle to Railway Station")
    assert reply is not None and "Bike Taxi request #1" in reply
    job=runtime.jobs.get(1)
    assert job["job_type"]=="BIKE"
    assert job["pickup_text"]=="Benz Circle"
    assert "Railway Station" in job["drop_text"]


def test_unrelated_message_not_hijacked(tmp_path):
    runtime=LocalMobilityRuntimeService(str(tmp_path/'u.db'),FakeUsers(),FakeWhatsApp())
    assert runtime.process("buyer","I need chicken 2 kg") is None
