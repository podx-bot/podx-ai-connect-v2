from types import SimpleNamespace

from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.universal_aware_conversation_service import UniversalAwareConversationService
from app.services.universal_live_capture_service import UniversalLiveCaptureService


class FakeExtractor:
    def __init__(self, request):
        self.request = request
        self.calls = []

    def extract(self, text):
        self.calls.append(text)
        return {"success": True, "request": dict(self.request)}


class FakeUsers:
    def __init__(self, user):
        self.user = dict(user)
        self.saved_locations = []

    def find_by_whatsapp_mobile(self, mobile):
        return dict(self.user)

    def save_location(self, **kwargs):
        self.saved_locations.append(kwargs)
        self.user["latitude"] = kwargs["latitude"]
        self.user["longitude"] = kwargs["longitude"]


class FakeSessions:
    def get(self, mobile):
        return SimpleNamespace(step=SimpleNamespace(name="MAIN_MENU"))


class FakeMatcher:
    def __init__(self, matches=None):
        self.matches = list(matches or [])
        self.calls = []

    def find_matches(self, request, limit=10):
        self.calls.append(dict(request))
        return list(self.matches)


class FakeTargeting:
    def __init__(self, total_targets=0):
        self.total_targets = total_targets

    def build_plan(self, request, already_contacted_user_ids=None, per_wave_limit=25):
        targets = [
            {"user_id": f"target-{i}", "score": 0.8, "distance_km": 2.0}
            for i in range(self.total_targets)
        ]
        return {
            "status": "TARGETED" if targets else "HOLD",
            "request_id": request.get("id"),
            "total_targets": len(targets),
            "waves": [{"wave": 1, "radius_km": 5, "targets": targets}] if targets else [],
        }


class FakeNotifications:
    def __init__(self):
        self.plans = []

    def dispatch_plan(self, request, plan):
        self.plans.append((dict(request), plan))
        sent = sum(len(w.get("targets") or []) for w in plan.get("waves") or [])
        return {"status": "NOTIFIED" if sent else "HOLD", "sent": sent}


class FakeNotificationRepo:
    def contacted_user_ids(self, request_id):
        return []


BASE_REQUEST = {
    "side": "NEED",
    "domain": "PRODUCT",
    "subject": "sona masoori rice",
    "quantity": 25,
    "unit": "kg",
    "price": 900,
    "currency": "INR",
    "when_text": None,
    "location_text": None,
    "location_required": True,
    "constraints": [],
    "confidence": 0.95,
}


def build_service(tmp_path, user, matches=None, targets=0):
    demands = UniversalDemandRepository(str(tmp_path / "podx.db"))
    extractor = FakeExtractor(BASE_REQUEST)
    notifications = FakeNotifications()
    service = UniversalLiveCaptureService(
        extractor=extractor,
        demand_repository=demands,
        matcher=FakeMatcher(matches),
        targeting_service=FakeTargeting(targets),
        notification_service=notifications,
        notification_repository=FakeNotificationRepo(),
        user_repository=FakeUsers(user),
        session_registry=FakeSessions(),
    )
    return service, demands, extractor, notifications


def test_natural_requirement_is_saved_matched_and_notified(tmp_path):
    service, demands, extractor, notifications = build_service(
        tmp_path,
        user={"registration_complete": 1, "latitude": 16.50, "longitude": 80.64, "area": "Vijayawada"},
        matches=[{"id": 9, "user_id": "seller-1", "score": 0.91, "distance_km": 1.4}],
    )

    reply = service.process_text("buyer-1", "నాకు సోనా మసూరి 25kg ₹900లో కావాలి")

    active = demands.list_active()
    assert len(active) == 1
    assert active[0]["user_id"] == "buyer-1"
    assert active[0]["subject"] == "sona masoori rice"
    assert active[0]["latitude"] == 16.50
    assert "1" in reply
    assert "notification" in reply
    assert len(notifications.plans) == 1
    assert notifications.plans[0][1]["waves"][0]["targets"][0]["user_id"] == "seller-1"


def test_missing_location_is_asked_once_then_matching_continues_on_share(tmp_path):
    service, demands, extractor, notifications = build_service(
        tmp_path,
        user={"registration_complete": 1, "latitude": None, "longitude": None},
        targets=2,
    )

    first = service.process_text("buyer-1", "నాకు బియ్యం కావాలి")
    assert "Location share" in first
    pending = demands.latest_active_for_user_missing_location("buyer-1")
    assert pending is not None

    second = service.handle_location(
        sender_mobile="buyer-1",
        latitude=16.51,
        longitude=80.65,
        location_name="Vijayawada",
    )
    stored = demands.get(int(pending["id"]))
    assert stored["latitude"] == 16.51
    assert stored["longitude"] == 80.65
    assert "Location save" in second
    assert "2" in second
    assert len(notifications.plans) == 1


def test_related_profiles_are_targeted_when_direct_match_is_absent(tmp_path):
    service, demands, extractor, notifications = build_service(
        tmp_path,
        user={"registration_complete": 1, "latitude": 16.50, "longitude": 80.64},
        matches=[],
        targets=3,
    )
    reply = service.process_text("buyer-1", "నాకు బియ్యం కావాలి")
    assert "Direct match" in reply
    assert "3" in reply
    assert len(notifications.plans) == 1


def test_greeting_and_low_level_flow_fall_back_instead_of_ai_capture(tmp_path):
    service, demands, extractor, notifications = build_service(
        tmp_path,
        user={"registration_complete": 1, "latitude": 16.50, "longitude": 80.64},
    )
    assert service.process_text("u1", "Hi") is None
    assert extractor.calls == []
    assert demands.list_active() == []


def test_universal_aware_adapter_order_is_response_then_capture_then_base():
    calls = []

    class Responses:
        def process_text(self, **kwargs):
            calls.append("response")
            return None

    class Capture:
        def process_text(self, **kwargs):
            calls.append("capture")
            return "captured"

    class Base:
        def process(self, **kwargs):
            calls.append("base")
            return "base"

    service = UniversalAwareConversationService(Responses(), Capture(), Base())
    assert service.process("1", "need rice") == "captured"
    assert calls == ["response", "capture"]
