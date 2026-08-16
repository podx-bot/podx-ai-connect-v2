from app.database.database import Database
from app.repositories.catering_catalog_repository import CateringCatalogRepository
from app.repositories.marketplace_repository import MarketplaceRepository
from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.event_master_rfq_service import EventMasterRFQService
from app.services.event_provider_runtime_service import EventProviderRuntimeService
from app.services.universal_rfq_service import UniversalRFQService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, recipient_mobile, message):
        self.sent.append((str(recipient_mobile), str(message)))
        return {"success": True}


def test_event_children_route_quote_compare_select(tmp_path):
    db_path = str(tmp_path / "event-provider.db")
    database = Database(db_path)
    database.create_tables()
    marketplace = MarketplaceRepository(database)
    catering = CateringCatalogRepository(db_path)
    rfqs = UniversalRFQRepository(db_path)
    rfq_service = UniversalRFQService(rfqs)

    marketplace.save_service_provider_profile(
        provider_mobile="decor1", service_name="Decoration", details="Stage and flowers",
        area="Vijayawada", source_message="I provide decoration",
    )
    catering.enable_provider("caterer1", "Sai Caterers")
    catering.add_item("caterer1", "Chicken Biryani")

    contacts = {
        "buyer": {"mobile": "buyer", "latitude": 16.50, "longitude": 80.64},
        "decor1": {"mobile": "decor1", "latitude": 16.51, "longitude": 80.65},
        "caterer1": {"mobile": "caterer1", "latitude": 16.52, "longitude": 80.66},
    }
    whatsapp = FakeWhatsApp()
    runtime = EventProviderRuntimeService(
        rfqs, rfq_service, marketplace, catering, whatsapp,
        lambda user_id: contacts.get(str(user_id), {"mobile": str(user_id)}),
    )
    event = EventMasterRFQService(rfqs).create_master_event(
        "buyer", "Marriage", 300, "Vijayawada", ["catering", "decoration"], "2026-12-20"
    )
    routed = runtime.route_children(event)
    assert routed["by_service"]["CATERING"] == 1
    assert routed["by_service"]["DECORATION"] == 1
    assert any(mobile == "decor1" and "EQUOTE" in body for mobile, body in whatsapp.sent)
    assert any(mobile == "caterer1" and "EQUOTE" in body for mobile, body in whatsapp.sent)

    decoration_rfq = next(row["rfq_id"] for row in event["children"] if row["service"] == "DECORATION")
    quote_reply = runtime.process("decor1", f"EQUOTE {decoration_rfq} 25000")
    assert "submit" in quote_reply
    compare_reply = runtime.process("buyer", f"ECOMPARE {decoration_rfq}")
    assert "₹25000" in compare_reply
    quote_id = rfqs.submitted_quotes(decoration_rfq)[0]["id"]
    select_reply = runtime.process("buyer", f"ESELECT {decoration_rfq} {quote_id}")
    assert "select" in select_reply
    assert rfqs.get_rfq(decoration_rfq)["status"] == "SELECTED"
    database.close()


def test_event_provider_cannot_quote_untargeted_rfq(tmp_path):
    db_path = str(tmp_path / "event-provider-guard.db")
    database = Database(db_path); database.create_tables()
    marketplace = MarketplaceRepository(database); catering = CateringCatalogRepository(db_path)
    rfqs = UniversalRFQRepository(db_path); service = UniversalRFQService(rfqs)
    whatsapp = FakeWhatsApp()
    runtime = EventProviderRuntimeService(rfqs, service, marketplace, catering, whatsapp, lambda x: {"mobile": str(x)})
    event = EventMasterRFQService(rfqs).create_master_event("buyer", "Birthday", 100, "Vuyyuru", ["sound"])
    sound_rfq = event["children"][0]["rfq_id"]
    reply = runtime.process("random", f"EQUOTE {sound_rfq} 10000")
    assert "active quotation request" in reply
    database.close()
