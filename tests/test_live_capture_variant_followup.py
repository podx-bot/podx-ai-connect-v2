from types import SimpleNamespace

from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.universal_live_capture_service import UniversalLiveCaptureService


class FailIfExtracted:
    def __init__(self):
        self.calls = []

    def extract(self, text):
        self.calls.append(text)
        raise AssertionError("variant follow-up must reuse the active request before generic extraction")


class FakeUsers:
    def find_by_whatsapp_mobile(self, mobile):
        return {"registration_complete": 1, "latitude": 16.50, "longitude": 80.64}


class FakeSessions:
    def get(self, mobile):
        return SimpleNamespace(step=SimpleNamespace(name="MAIN_MENU"))


class FakeMatcher:
    def __init__(self):
        self.calls = []

    def find_matches(self, request, limit=10):
        self.calls.append(dict(request))
        return []


class FakeTargeting:
    def build_plan(self, request, already_contacted_user_ids=None, per_wave_limit=25):
        return {"status": "HOLD", "request_id": request.get("id"), "total_targets": 0, "waves": []}


class FakeNotifications:
    def dispatch_plan(self, request, plan):
        return {"status": "HOLD", "sent": 0}


class FakeNotificationRepo:
    def contacted_user_ids(self, request_id):
        return []


def test_boneless_followup_revises_active_chicken_request_and_preserves_quantity(tmp_path):
    demands = UniversalDemandRepository(str(tmp_path / "podx.db"))
    original_id = demands.create(
        {
            "user_id": "buyer-1",
            "side": "NEED",
            "domain": "PRODUCT",
            "subject": "chicken",
            "quantity": 10.0,
            "unit": "kg",
            "price": None,
            "currency": "INR",
            "when_text": None,
            "latitude": 16.50,
            "longitude": 80.64,
            "location_text": "Vijayawada",
            "constraints": {},
            "source": "text",
            "status": "ACTIVE",
        }
    )
    extractor = FailIfExtracted()
    matcher = FakeMatcher()
    service = UniversalLiveCaptureService(
        extractor=extractor,
        demand_repository=demands,
        matcher=matcher,
        targeting_service=FakeTargeting(),
        notification_service=FakeNotifications(),
        notification_repository=FakeNotificationRepo(),
        user_repository=FakeUsers(),
        session_registry=FakeSessions(),
    )

    reply = service.process_text("buyer-1", "బోన్లెస్ కావాలి")

    original = demands.get(original_id)
    latest = demands.latest_active_for_user("buyer-1")
    assert original["status"] == "REVISED"
    assert latest is not None
    assert latest["id"] != original_id
    assert latest["subject"] == "chicken"
    assert latest["quantity"] == 10.0
    assert latest["unit"] == "kg"
    assert latest["side"] == "NEED"
    assert latest["constraints"]["variant"] == "boneless"
    assert extractor.calls == []
    assert matcher.calls[-1]["subject"] == "chicken"
    assert matcher.calls[-1]["quantity"] == 10.0
    assert matcher.calls[-1]["constraints"]["variant"] == "boneless"
    assert "boneless preference add" in reply
    assert "quantity/details అలాగే" in reply
