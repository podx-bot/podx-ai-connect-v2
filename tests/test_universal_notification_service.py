from app.repositories.universal_notification_repository import UniversalNotificationRepository
from app.services.universal_notification_service import UniversalNotificationService


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_text_message(self, mobile, message):
        self.sent.append((mobile, message))
        return {"success": True, "provider_message_id": f"msg-{len(self.sent)}"}


def _contacts(user_id):
    data = {
        "buyer": {"name": "Buyer", "mobile": "9100000001"},
        "seller": {"name": "Seller", "mobile": "9100000002"},
    }
    return data.get(user_id)


def test_dispatch_deduplicates_same_target(tmp_path):
    repo = UniversalNotificationRepository(str(tmp_path / "notify.db"))
    wa = FakeWhatsApp()
    service = UniversalNotificationService(repo, wa, _contacts)
    request = {"id": 11, "user_id": "buyer", "subject": "sona masoori rice", "quantity": 25, "unit": "kg"}
    plan = {"waves": [{"wave": 1, "targets": [{"user_id": "seller", "score": 0.9, "distance_km": 1.2}]}]}

    first = service.dispatch_plan(request, plan)
    second = service.dispatch_plan(request, plan)

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped_duplicate"] == 1
    assert repo.contacted_user_ids(11) == ["seller"]


def test_interest_then_consent_shares_both_contacts_once(tmp_path):
    repo = UniversalNotificationRepository(str(tmp_path / "notify.db"))
    wa = FakeWhatsApp()
    service = UniversalNotificationService(repo, wa, _contacts)
    request = {"id": 12, "user_id": "buyer", "subject": "rice bag"}

    interest = service.register_interest(request, "seller")
    assert interest["status"] == "WAITING_REQUESTER_CONSENT"

    shared = service.confirm_and_share_contacts(request, "seller", True)
    assert shared["status"] == "CONTACT_SHARED"
    assert any("9100000002" in text for _, text in wa.sent)
    assert any("9100000001" in text for _, text in wa.sent)

    repeated = service.confirm_and_share_contacts(request, "seller", True)
    assert repeated["status"] == "ALREADY_SHARED"


def test_requester_can_decline_contact_exchange(tmp_path):
    repo = UniversalNotificationRepository(str(tmp_path / "notify.db"))
    wa = FakeWhatsApp()
    service = UniversalNotificationService(repo, wa, _contacts)
    request = {"id": 13, "user_id": "buyer", "subject": "electrician"}
    service.register_interest(request, "seller")

    result = service.confirm_and_share_contacts(request, "seller", False)
    assert result["status"] == "DECLINED"
    assert repo.get_interest(13, "seller")["requester_status"] == "REJECTED"
    assert repo.get_interest(13, "seller")["contact_shared"] == 0
