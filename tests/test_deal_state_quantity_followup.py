from types import SimpleNamespace

from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.universal_live_capture_service import UniversalLiveCaptureService


class FakeExtractor:
    def __init__(self):
        self.calls = []

    def extract(self, text):
        self.calls.append(text)
        return {
            "success": True,
            "request": {
                "side": "NEED",
                "domain": "PRODUCT",
                "subject": "new product",
                "quantity": 10,
                "unit": "kg",
                "confidence": 0.95,
            },
        }


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile):
        return {
            "registration_complete": 1,
            "latitude": 16.50,
            "longitude": 80.64,
            "area": "Vijayawada",
        }


class FakeSessions:
    def get(self, mobile):
        return SimpleNamespace(step=SimpleNamespace(name="MAIN_MENU"))


class FakeMatcher:
    def __init__(self):
        self.calls = []

    def find_matches(self, request, limit=10):
        self.calls.append(dict(request))
        return [{"id": 9, "user_id": "seller-1", "score": 0.91, "distance_km": 1.0}]


class FakeTargeting:
    def build_plan(self, request, already_contacted_user_ids=None, per_wave_limit=25):
        return {"status": "HOLD", "request_id": request.get("id"), "total_targets": 0, "waves": []}


class FakeNotifications:
    def __init__(self):
        self.plans = []

    def dispatch_plan(self, request, plan):
        self.plans.append((dict(request), plan))
        return {"status": "NOTIFIED", "sent": 1, "failed": 0, "skipped_duplicate": 0}


class FakeNotificationRepo:
    def contacted_user_ids(self, request_id):
        return []


def build_service(tmp_path):
    demands = UniversalDemandRepository(str(tmp_path / "podx.db"))
    extractor = FakeExtractor()
    matcher = FakeMatcher()
    notifications = FakeNotifications()
    service = UniversalLiveCaptureService(
        extractor=extractor,
        demand_repository=demands,
        matcher=matcher,
        targeting_service=FakeTargeting(),
        notification_service=notifications,
        notification_repository=FakeNotificationRepo(),
        user_repository=FakeUsers(),
        session_registry=FakeSessions(),
    )
    return service, demands, extractor, matcher, notifications


def test_quantity_only_followup_preserves_active_product_and_rematches(tmp_path):
    service, demands, extractor, matcher, notifications = build_service(tmp_path)
    old_id = demands.create({
        "user_id": "buyer-1",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "chicken",
        "quantity": 5,
        "unit": "kg",
        "latitude": 16.50,
        "longitude": 80.64,
        "location_text": "Vijayawada",
        "status": "ACTIVE",
    })

    reply = service.process_text("buyer-1", "10 కిలోలు కావాలి")

    assert extractor.calls == []
    assert demands.get(old_id)["status"] == "REVISED"
    active = demands.latest_active_for_user("buyer-1")
    assert active is not None
    assert active["id"] != old_id
    assert active["side"] == "NEED"
    assert active["domain"] == "PRODUCT"
    assert active["subject"] == "chicken"
    assert active["quantity"] == 10
    assert active["unit"] == "kg"
    assert matcher.calls[-1]["subject"] == "chicken"
    assert matcher.calls[-1]["quantity"] == 10
    assert notifications.plans[-1][0]["id"] == active["id"]
    assert "chicken quantity 10 kg" in reply
    assert "1 seller match" in reply


def test_full_product_message_is_not_mistaken_for_quantity_only_followup(tmp_path):
    service, demands, extractor, matcher, notifications = build_service(tmp_path)
    old_id = demands.create({
        "user_id": "buyer-1",
        "side": "NEED",
        "domain": "PRODUCT",
        "subject": "chicken",
        "quantity": 5,
        "unit": "kg",
        "latitude": 16.50,
        "longitude": 80.64,
        "status": "ACTIVE",
    })

    service.process_text("buyer-1", "10 kg rice కావాలి")

    assert extractor.calls == ["10 kg rice కావాలి"]
    assert demands.get(old_id)["status"] == "ACTIVE"
