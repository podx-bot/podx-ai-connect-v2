from app.repositories.proactive_alert_preference_repository import ProactiveAlertPreferenceRepository
from app.services.demand_intelligence_service import DemandIntelligenceService
from app.services.proactive_alert_preference_service import ProactiveAlertPreferenceService
from app.services.smart_reengagement_service import SmartReengagementService
from app.services.street_vendor_proximity_service import StreetVendorProximityService


class FakePrefs:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def is_enabled(self, user_id):
        return self.enabled


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, *args, **kwargs):
        mobile = kwargs.get("recipient_mobile") or (args[0] if args else "")
        message = kwargs.get("message") or (args[1] if len(args) > 1 else "")
        self.sent.append((str(mobile), str(message)))
        return {"success": True}


class FakeDemandRows:
    db_path = ""

    def list_active(self, *args, **kwargs):
        return [
            {"id": 1, "side": "NEED", "domain": "PRODUCT", "subject": "rice", "location_text": "Vuyyuru", "user_id": "buyer", "latitude": 16.36, "longitude": 80.84},
            {"id": 2, "side": "NEED", "domain": "PRODUCT", "subject": "rice", "location_text": "Vuyyuru", "user_id": "buyer2", "latitude": 16.36, "longitude": 80.84},
        ]


class FakeTargeting:
    def build_plan(self, request, already_contacted_user_ids, per_wave_limit):
        return {"waves": [{"targets": [{"user_id": "seller"}]}]}


class FakeSignals:
    def __init__(self):
        self.claims = 0

    def claim(self, *args):
        self.claims += 1
        return True


class FakeCatalog:
    db_path = ""

    def get(self, product_id):
        return {"id": 10, "active": 1, "stock_status": "IN_STOCK", "subject": "rice", "price": 50}


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile):
        rows = {
            "seller": {"whatsapp_mobile": "seller", "location_name": "Vuyyuru"},
            "buyer": {"whatsapp_mobile": "buyer"},
        }
        return rows.get(str(mobile), {})


class FakeLedger:
    def __init__(self):
        self.claims = 0

    def claim(self, **kwargs):
        self.claims += 1
        return True

    def release(self, *args):
        pass


class FakeVendorRepo:
    db_path = ""

    def __init__(self):
        self.saved = 0

    def alert_record(self, *args):
        return None

    def save_alert(self, *args):
        self.saved += 1


class FakeVendorDemands:
    def list_active(self, *args, **kwargs):
        return [{"id": 7, "side": "NEED", "domain": "PRODUCT", "subject": "vegetables", "user_id": "buyer", "latitude": 16.3601, "longitude": 80.8401}]


def test_preferences_default_on_and_persist_off(tmp_path):
    db = str(tmp_path / "prefs.db")
    first = ProactiveAlertPreferenceRepository(db)
    assert first.is_enabled("user1") is True
    first.set_enabled("user1", False)
    second = ProactiveAlertPreferenceRepository(db)
    assert second.is_enabled("user1") is False
    second.set_enabled("user1", True)
    assert first.is_enabled("user1") is True


def test_alert_commands_only_pause_optional_discovery(tmp_path):
    repo = ProactiveAlertPreferenceRepository(str(tmp_path / "commands.db"))
    service = ProactiveAlertPreferenceService(repo)
    reply = service.process("user1", "ALERTS OFF")
    assert repo.is_enabled("user1") is False
    assert "Orders" in reply and "ALWAYS" not in reply
    status = service.process("user1", "alerts status")
    assert "OFF" in status and "ALWAYS ON" in status
    service.process("user1", "అలర్ట్స్ ఆన్")
    assert repo.is_enabled("user1") is True
    assert service.process("user1", "I need rice") is None


def test_demand_signal_not_claimed_when_target_opted_out():
    signals = FakeSignals()
    whatsapp = FakeWhatsApp()
    service = DemandIntelligenceService(
        FakeDemandRows(), FakeTargeting(), signals, whatsapp,
        contact_resolver=lambda user_id: {"mobile": user_id},
        alert_preferences=FakePrefs(False),
    )
    result = service.scan_and_notify()
    assert result["notified"] == 0
    assert signals.claims == 0
    assert whatsapp.sent == []


def test_reengagement_skips_before_dedupe_claim_when_buyer_opted_out():
    ledger = FakeLedger()
    whatsapp = FakeWhatsApp()
    service = SmartReengagementService(
        FakeDemandRows(), FakeCatalog(), FakeUsers(), ledger, whatsapp,
        alert_preferences=FakePrefs(False),
    )
    result = service.notify_product_available("seller", 10)
    assert result["sent"] == 0
    assert ledger.claims == 0
    assert whatsapp.sent == []


def test_street_vendor_skips_opted_out_nearby_buyer():
    repo = FakeVendorRepo()
    whatsapp = FakeWhatsApp()
    service = StreetVendorProximityService(
        repo, FakeVendorDemands(), FakeUsers(), whatsapp,
        alert_preferences=FakePrefs(False),
    )
    sent = service._notify_relevant_buyers({
        "vendor_mobile": "vendor", "items_text": "vegetables fruits",
        "latitude": 16.36, "longitude": 80.84,
    })
    assert sent == 0
    assert repo.saved == 0
    assert whatsapp.sent == []
