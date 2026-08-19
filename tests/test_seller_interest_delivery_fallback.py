from app.services.reliable_universal_notification_service import ReliableUniversalNotificationService


class _Repo:
    def record_interest(self, request_id, buyer, seller):
        self.recorded = (request_id, buyer, seller)


class _WhatsApp:
    def __init__(self, interactive_success=False, text_success=True):
        self.interactive_success = interactive_success
        self.text_success = text_success
        self.calls = []

    def send_reply_buttons(self, mobile, body, buttons):
        self.calls.append(("buttons", str(mobile), str(body)))
        return {"success": self.interactive_success, "status": "PROVIDER_HTTP_ERROR" if not self.interactive_success else "SENT_TO_PROVIDER"}

    def send_text_message(self, mobile, body):
        self.calls.append(("text", str(mobile), str(body)))
        return {"success": self.text_success, "status": "SENT_TO_PROVIDER" if self.text_success else "PROVIDER_HTTP_ERROR"}


def _contact(user_id):
    return {"mobile": str(user_id), "name": str(user_id)}


def test_seller_interest_falls_back_to_plain_text_when_buttons_fail():
    repo = _Repo()
    wa = _WhatsApp(interactive_success=False, text_success=True)
    service = ReliableUniversalNotificationService(repo, wa, _contact)
    request = {"id": 9, "user_id": "buyer", "side": "NEED", "subject": "chicken", "quantity": 5, "unit": "kg"}

    result = service.register_interest(request, "buyer", "seller")

    assert result["status"] == "WAITING_SELLER_CONFIRM"
    assert result["notification"]["success"] is True
    assert result["fallback_used"] is True
    assert [call[0] for call in wa.calls] == ["buttons", "text"]
    assert "CONFIRM" in wa.calls[-1][2]
    assert "DECLINE" in wa.calls[-1][2]


def test_seller_interest_reports_failure_when_all_delivery_paths_fail():
    repo = _Repo()
    wa = _WhatsApp(interactive_success=False, text_success=False)
    service = ReliableUniversalNotificationService(repo, wa, _contact)
    request = {"id": 9, "user_id": "buyer", "side": "NEED", "subject": "chicken"}

    result = service.register_interest(request, "buyer", "seller")

    assert result["status"] == "SELLER_NOTIFICATION_FAILED"
    assert result["notification"]["success"] is False
