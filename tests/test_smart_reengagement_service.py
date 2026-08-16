from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.repositories.reengagement_repository import ReengagementRepository
from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.smart_reengagement_service import SmartReengagementService


class FakeUsers:
    def __init__(self):
        self.rows = {
            "seller": {
                "whatsapp_mobile": "seller",
                "name": "Local Store",
                "business_name": "Local Store",
                "latitude": 16.5000,
                "longitude": 80.6400,
                "location_name": "Vijayawada",
            },
            "buyer": {
                "whatsapp_mobile": "buyer",
                "name": "Buyer",
                "latitude": 16.5100,
                "longitude": 80.6500,
                "location_name": "Vijayawada",
            },
            "far": {
                "whatsapp_mobile": "far",
                "name": "Far Buyer",
                "latitude": 17.4000,
                "longitude": 78.4800,
                "location_name": "Hyderabad",
            },
        }

    def find_by_whatsapp_mobile(self, mobile):
        return self.rows.get(str(mobile))


class FakeWhatsApp:
    def __init__(self, success=True):
        self.success = success
        self.sent = []

    def send_reply_buttons(self, mobile, body, buttons):
        self.sent.append((mobile, body, buttons))
        return {"success": self.success, "provider_message_id": "msg-1" if self.success else None}

    def send_text_message(self, mobile, body):
        self.sent.append((mobile, body, []))
        return {"success": self.success}


def _need(repo, user_id, lat, lon, subject="Basmati Rice", location="Vijayawada"):
    return repo.create({
        "user_id": user_id,
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": subject,
        "latitude": lat,
        "longitude": lon,
        "location_text": location,
        "source": "text",
    })


def test_reengagement_notifies_nearby_buyer_and_dedupes_same_state(tmp_path):
    db = str(tmp_path / "smart.db")
    demands = UniversalDemandRepository(db)
    catalog = ProductCatalogRepository(db)
    ledger = ReengagementRepository(db)
    users = FakeUsers()
    wa = FakeWhatsApp()
    _need(demands, "buyer", 16.5100, 80.6500)
    product_id = catalog.upsert_product("seller", "Basmati Rice", price=120, stock_status="IN_STOCK")
    service = SmartReengagementService(demands, catalog, users, ledger, wa, radius_km=25)

    first = service.notify_product_available("seller", product_id)
    second = service.notify_product_available("seller", product_id)

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert len(wa.sent) == 1
    assert wa.sent[0][0] == "buyer"
    assert "Basmati Rice" in wa.sent[0][1]
    assert wa.sent[0][2][0]["id"].startswith("BUY_INTERESTED ")


def test_reengagement_price_change_can_send_new_useful_alert(tmp_path):
    db = str(tmp_path / "price.db")
    demands = UniversalDemandRepository(db)
    catalog = ProductCatalogRepository(db)
    ledger = ReengagementRepository(db)
    users = FakeUsers()
    wa = FakeWhatsApp()
    _need(demands, "buyer", 16.5100, 80.6500)
    product_id = catalog.upsert_product("seller", "Basmati Rice", price=120, stock_status="IN_STOCK")
    service = SmartReengagementService(demands, catalog, users, ledger, wa)
    assert service.notify_product_available("seller", product_id)["sent"] == 1

    same_id = catalog.upsert_product("seller", "Basmati Rice", price=110, stock_status="IN_STOCK")
    assert same_id == product_id
    assert service.notify_product_available("seller", same_id)["sent"] == 1
    assert len(wa.sent) == 2
    assert "₹110" in wa.sent[-1][1]


def test_reengagement_skips_far_buyer(tmp_path):
    db = str(tmp_path / "far.db")
    demands = UniversalDemandRepository(db)
    catalog = ProductCatalogRepository(db)
    ledger = ReengagementRepository(db)
    users = FakeUsers()
    wa = FakeWhatsApp()
    _need(demands, "far", 17.4000, 78.4800, location="Hyderabad")
    product_id = catalog.upsert_product("seller", "Basmati Rice", price=120, stock_status="IN_STOCK")
    service = SmartReengagementService(demands, catalog, users, ledger, wa, radius_km=25)

    result = service.notify_product_available("seller", product_id)
    assert result["sent"] == 0
    assert wa.sent == []


def test_failed_delivery_releases_claim_for_retry(tmp_path):
    db = str(tmp_path / "retry.db")
    demands = UniversalDemandRepository(db)
    catalog = ProductCatalogRepository(db)
    ledger = ReengagementRepository(db)
    users = FakeUsers()
    wa = FakeWhatsApp(success=False)
    _need(demands, "buyer", 16.5100, 80.6500)
    product_id = catalog.upsert_product("seller", "Basmati Rice", price=120, stock_status="IN_STOCK")
    service = SmartReengagementService(demands, catalog, users, ledger, wa)

    assert service.notify_product_available("seller", product_id)["sent"] == 0
    wa.success = True
    assert service.notify_product_available("seller", product_id)["sent"] == 1
    assert len(wa.sent) == 2
