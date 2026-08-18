from types import SimpleNamespace

from app.services.universal_correction_service import UniversalCorrectionService


class FakeDB:
    def __init__(self, users):
        self.users = users
        self.audit = []

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split()).lower()
        if normalized.startswith("create table"):
            return None
        if "delete from user_capabilities" in normalized:
            self.users.capabilities[str(params[0])] = []
            return None
        if normalized.startswith("update users set name="):
            value, sender = params
            self.users.records[str(sender)]["name"] = value
            return None
        if normalized.startswith("update users set language="):
            value, sender = params
            self.users.records[str(sender)]["language"] = value
            return None
        if normalized.startswith("update users set area="):
            value, sender = params
            self.users.records[str(sender)]["area"] = value
            return None
        if "insert into user_correction_audit" in normalized:
            self.audit.append(params)
            return None
        return None


class FakeUsers:
    def __init__(self):
        self.records = {
            "u1": {
                "whatsapp_mobile": "u1",
                "registration_complete": 1,
                "name": "Manohar",
                "language": "Telugu",
                "area": "Vuyyuru",
            }
        }
        self.capabilities = {"u1": ["BUYER"]}
        self.database = FakeDB(self)

    def find_by_whatsapp_mobile(self, sender):
        row = dict(self.records.get(str(sender)) or {})
        if not row:
            return None
        row["capabilities"] = list(self.capabilities.get(str(sender), []))
        return row

    def add_capabilities(self, sender, capabilities, source=None):
        current = self.capabilities.setdefault(str(sender), [])
        for capability in capabilities:
            if capability not in current:
                current.append(capability)


class FakeSessions:
    def __init__(self):
        self.session = SimpleNamespace(
            step=SimpleNamespace(name="MAIN_MENU"),
            data={"registration_capabilities": ["BUYER"]},
        )

    def get(self, sender):
        return self.session


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "delegated"


def make_service():
    users = FakeUsers()
    sessions = FakeSessions()
    delegate = Delegate()
    service = UniversalCorrectionService(delegate, users, sessions)
    return service, users, sessions, delegate


def test_sorry_7_replaces_recent_registration_role_with_all():
    service, users, sessions, delegate = make_service()

    reply = service.process("u1", "Sorry 7")

    assert users.capabilities["u1"] == [
        "BUYER",
        "SELLER",
        "SERVICE_CUSTOMER",
        "SERVICE_PROVIDER",
        "WORKER",
        "EMPLOYER",
    ]
    assert "roles మార్చాను" in reply
    assert delegate.calls == []
    assert sessions.session.data["last_corrected_field"] == "roles"


def test_numeric_role_correction_replaces_not_adds():
    service, users, _, _ = make_service()
    users.capabilities["u1"] = ["BUYER", "SELLER"]

    service.process("u1", "actually 5")

    assert users.capabilities["u1"] == ["WORKER"]


def test_explicit_language_correction_updates_profile_and_audits():
    service, users, _, _ = make_service()

    reply = service.process("u1", "sorry language English")

    assert users.records["u1"]["language"] == "English"
    assert "Telugu → English" in reply
    assert users.database.audit


def test_transaction_quantity_correction_falls_through_to_active_runtime():
    service, _, _, delegate = make_service()

    reply = service.process("u1", "sorry quantity 10 kg కాదు 15 kg")

    assert reply == "delegated"
    assert delegate.calls == [("u1", "sorry quantity 10 kg కాదు 15 kg")]


def test_normal_message_is_not_intercepted():
    service, _, _, delegate = make_service()

    reply = service.process("u1", "Chicken కొనాలి")

    assert reply == "delegated"
    assert delegate.calls == [("u1", "Chicken కొనాలి")]
