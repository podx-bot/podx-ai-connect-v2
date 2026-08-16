from app.services.local_dispatch_runtime_service import LocalDispatchRuntimeService


class FakeDatabase:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self, query, args=()):
        return self.rows


class FakeUsers:
    def __init__(self):
        self.database = FakeDatabase([
            {"whatsapp_mobile": "partner-1", "registration_complete": 1, "latitude": 16.50, "longitude": 80.64, "updated_at": "now"},
            {"whatsapp_mobile": "partner-2", "registration_complete": 1, "latitude": 16.51, "longitude": 80.65, "updated_at": "now"},
        ])
        self.users = {
            "partner-1": {"whatsapp_mobile": "partner-1", "registration_complete": 1, "latitude": 16.50, "longitude": 80.64},
            "partner-2": {"whatsapp_mobile": "partner-2", "registration_complete": 1, "latitude": 16.51, "longitude": 80.65},
        }
        self.capabilities = {"partner-1": {"DELIVERY_PARTNER"}, "partner-2": {"DELIVERY_PARTNER"}}

    def find_by_whatsapp_mobile(self, user_id):
        return self.users.get(user_id)

    def add_capability(self, user_id, capability, source=None):
        self.capabilities.setdefault(user_id, set()).add(capability)

    def has_capability(self, user_id, capability):
        return capability in self.capabilities.get(user_id, set())


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_reply_buttons(self, mobile, body, buttons):
        self.sent.append((mobile, body, buttons))
        return {"success": True}

    def send_text_message(self, mobile, message):
        self.sent.append((mobile, message, None))
        return {"success": True}


class FakeDispatch:
    def __init__(self):
        self.task = {
            "id": 7,
            "status": "OPEN",
            "seller_user_id": "seller",
            "buyer_user_id": "buyer",
            "pickup_lat": 16.50,
            "pickup_lon": 80.64,
            "pickup_text": "Vijayawada Shop",
            "drop_text": "Benz Circle",
            "fee": 50,
            "assigned_partner_id": None,
        }
        self.offers = set()

    def get(self, task_id):
        return dict(self.task) if int(task_id) == 7 else None

    def offer(self, task_id, partner_user_id, distance_km=None):
        self.offers.add(str(partner_user_id))

    def claim(self, task_id, partner_user_id):
        if self.task["status"] != "OPEN" or str(partner_user_id) not in self.offers:
            return False
        self.task["status"] = "ACCEPTED"
        self.task["assigned_partner_id"] = str(partner_user_id)
        return True

    def update_status(self, task_id, partner_user_id, status):
        if self.task.get("assigned_partner_id") != str(partner_user_id):
            return False
        self.task["status"] = status
        return True


def contact(user_id):
    return {"mobile": user_id, "name": user_id.title()}


def build():
    dispatch = FakeDispatch()
    users = FakeUsers()
    whatsapp = FakeWhatsApp()
    service = LocalDispatchRuntimeService(dispatch, users, whatsapp, contact)
    return service, dispatch, users, whatsapp


def test_nearby_partners_receive_offer_and_first_accepter_wins():
    service, dispatch, users, whatsapp = build()
    result = service.offer_task(7)
    assert result["offered"] == 2
    assert dispatch.offers == {"partner-1", "partner-2"}

    first = service.process("partner-1", "DTAKE 7")
    second = service.process("partner-2", "DTAKE 7")
    assert "assign" in first
    assert "ఇప్పటికే" in second
    assert dispatch.task["assigned_partner_id"] == "partner-1"


def test_partner_delivery_status_chain_and_completion_notifies_buyer_seller():
    service, dispatch, users, whatsapp = build()
    service.offer_task(7)
    service.process("partner-1", "DTAKE 7")
    assert "Pickup" in service.process("partner-1", "DPICKUP 7")
    assert "On the way" in service.process("partner-1", "DONWAY 7")
    reply = service.process("partner-1", "DDELIVERED 7")
    assert "completed" in reply
    assert dispatch.task["status"] == "DELIVERED"
    assert any(row[0] == "buyer" and "complete" in row[1] for row in whatsapp.sent)
    assert any(row[0] == "seller" and "complete" in row[1] for row in whatsapp.sent)


def test_delivery_on_adds_partner_capability():
    service, dispatch, users, whatsapp = build()
    users.capabilities["partner-1"] = set()
    reply = service.process("partner-1", "DELIVERY ON")
    assert "mode ON" in reply
    assert users.has_capability("partner-1", "DELIVERY_PARTNER")
