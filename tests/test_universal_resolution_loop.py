from types import SimpleNamespace

from app.repositories.universal_demand_repository import UniversalDemandRepository
from app.services.universal_live_capture_service import UniversalLiveCaptureService
from app.services.universal_matcher import UniversalMatcher


class FakeUsers:
    def __init__(self):
        self.rows = {
            "buyer-1": {
                "registration_complete": 1,
                "latitude": 16.50,
                "longitude": 80.64,
                "area": "Vijayawada",
            },
            "seller-1": {
                "registration_complete": 1,
                "latitude": 16.51,
                "longitude": 80.65,
                "area": "Vijayawada",
            },
        }

    def find_by_whatsapp_mobile(self, mobile):
        return dict(self.rows.get(mobile) or {})


class FakeSessions:
    def get(self, mobile):
        return SimpleNamespace(step=SimpleNamespace(name="MAIN_MENU"))


class NoopTargeting:
    def build_plan(self, request, already_contacted_user_ids=None, per_wave_limit=25):
        return {
            "status": "HOLD",
            "request_id": request.get("id"),
            "total_targets": 0,
            "waves": [],
        }


class FakeNotificationRepository:
    def contacted_user_ids(self, request_id):
        return []


class FakeNotifications:
    def __init__(self):
        self.plans = []

    def dispatch_plan(self, request, plan):
        self.plans.append((dict(request), plan))
        sent = sum(len(wave.get("targets") or []) for wave in plan.get("waves") or [])
        return {"status": "NOTIFIED" if sent else "HOLD", "sent": sent}


def build_service(tmp_path):
    repository = UniversalDemandRepository(str(tmp_path / "podx.db"))
    notifications = FakeNotifications()
    service = UniversalLiveCaptureService(
        extractor=None,
        demand_repository=repository,
        matcher=UniversalMatcher(repository),
        targeting_service=NoopTargeting(),
        notification_service=notifications,
        notification_repository=FakeNotificationRepository(),
        user_repository=FakeUsers(),
        session_registry=FakeSessions(),
    )
    return service, repository, notifications


def test_future_offer_automatically_reaches_waiting_buyer(tmp_path):
    service, repository, notifications = build_service(tmp_path)

    need_reply = service.process_structured(
        "buyer-1",
        {
            "side": "NEED",
            "domain": "PRODUCT",
            "subject": "water pump",
            "quantity": 1,
            "unit": "piece",
            "confidence": 0.95,
            "constraints": [],
        },
    )

    waiting = repository.list_active()
    assert len(waiting) == 1
    assert waiting[0]["user_id"] == "buyer-1"
    assert "direct match" in need_reply.casefold()
    assert notifications.plans == []

    offer_reply = service.process_structured(
        "seller-1",
        {
            "side": "OFFER",
            "domain": "PRODUCT",
            "subject": "water pump",
            "quantity": 2,
            "unit": "piece",
            "price": 2500,
            "currency": "INR",
            "confidence": 0.96,
            "constraints": [],
        },
    )

    assert "buyer match" in offer_reply.casefold()
    assert len(notifications.plans) == 1
    request, plan = notifications.plans[0]
    assert request["side"] == "OFFER"
    targets = plan["waves"][0]["targets"]
    assert [target["user_id"] for target in targets] == ["buyer-1"]


def test_waiting_need_remains_active_until_conversion_lifecycle_finishes(tmp_path):
    service, repository, _ = build_service(tmp_path)

    service.process_structured(
        "buyer-1",
        {
            "side": "NEED",
            "domain": "SERVICE",
            "subject": "solar inverter repair",
            "confidence": 0.94,
            "constraints": [],
        },
    )

    active = repository.list_active()
    assert len(active) == 1
    assert active[0]["status"] == "ACTIVE"
    assert active[0]["subject"] == "solar inverter repair"
