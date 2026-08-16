from app.repositories.catering_catalog_repository import CateringCatalogRepository
from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.catering_rfq_runtime_service import CateringRFQRuntimeService
from app.services.universal_rfq_service import UniversalRFQService


class FakeUsers:
    def __init__(self):
        self.rows = {
            "buyer": {"whatsapp_mobile": "buyer", "registration_complete": 1},
            "caterer-a": {"whatsapp_mobile": "caterer-a", "registration_complete": 1},
            "caterer-b": {"whatsapp_mobile": "caterer-b", "registration_complete": 1},
        }
        self.capabilities = {}

    def find_by_whatsapp_mobile(self, user_id):
        return self.rows.get(user_id)

    def add_capability(self, user_id, capability, source=None):
        self.capabilities.setdefault(user_id, set()).add(capability)


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, message):
        self.sent.append((str(mobile), str(message)))
        return {"success": True, "provider_message_id": f"m-{len(self.sent)}"}


def contacts(user_id):
    data = {
        "buyer": {"mobile": "buyer", "name": "Buyer", "latitude": 16.50, "longitude": 80.64},
        "caterer-a": {"mobile": "caterer-a", "name": "A Caterers", "latitude": 16.51, "longitude": 80.65},
        "caterer-b": {"mobile": "caterer-b", "name": "B Caterers", "latitude": 16.52, "longitude": 80.66},
    }
    return data.get(user_id, {"mobile": user_id, "name": user_id})


def build(tmp_path):
    db = str(tmp_path / "podx.db")
    catalog = CateringCatalogRepository(db)
    rfqs = UniversalRFQRepository(db)
    rfq_service = UniversalRFQService(rfqs)
    whatsapp = FakeWhatsApp()
    users = FakeUsers()
    runtime = CateringRFQRuntimeService(catalog, rfqs, rfq_service, whatsapp, contacts, user_repository=users)
    return runtime, catalog, rfqs, whatsapp, users


def test_catering_catalog_rfq_quote_compare_select_end_to_end(tmp_path):
    runtime, catalog, rfqs, whatsapp, users = build(tmp_path)

    assert "profile ON" in runtime.process("caterer-a", "CATERER ON")
    assert "3 item" in runtime.process("caterer-a", "CMENU Chicken Biryani, Paneer Curry, Sweet")
    assert "profile ON" in runtime.process("caterer-b", "CATERER ON")
    assert "2 item" in runtime.process("caterer-b", "CMENU Chicken Biryani, Paneer Curry")

    buyer_reply = runtime.process(
        "buyer",
        "CRFQ 300 | Vijayawada | Chicken Biryani, Paneer Curry, Sweet",
    )
    assert "Catering RFQ #1" in buyer_reply
    assert "2 matching caterer" in buyer_reply
    assert any(to == "caterer-a" and "Your catalog match: 3/3" in msg for to, msg in whatsapp.sent)
    assert any(to == "caterer-b" and "Your catalog match: 2/3" in msg for to, msg in whatsapp.sent)

    quote_a = runtime.process("caterer-a", "CQUOTE 1 120000")
    quote_b = runtime.process("caterer-b", "CQUOTE 1 90000")
    assert "coverage 3/3" in quote_a
    assert "coverage 2/3" in quote_b

    comparison = runtime.process("buyer", "CCOMPARE 1")
    lines = comparison.splitlines()
    assert "caterer-a" in lines[1]
    assert "100.0% match" in lines[1]
    assert "caterer-b" in comparison
    assert "Sweet" in comparison

    selected = runtime.process("buyer", "CSELECT 1 1")
    assert "Quote #1 select" in selected
    assert rfqs.get_rfq(1)["status"] == "SELECTED"
    assert any(to == "caterer-a" and "select అయింది" in msg for to, msg in whatsapp.sent)


def test_catering_menu_is_saved_once_and_listable(tmp_path):
    runtime, catalog, rfqs, whatsapp, users = build(tmp_path)
    runtime.process("caterer-a", "CATERER ON")
    runtime.process("caterer-a", "CMENU Chicken Biryani, Sweet, Chicken Biryani")
    items = catalog.list_items("caterer-a")
    assert len(items) == 2
    listed = runtime.process("caterer-a", "CLIST")
    assert "Chicken Biryani" in listed
    assert "Sweet" in listed
