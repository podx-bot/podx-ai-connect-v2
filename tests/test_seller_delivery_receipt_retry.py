from app.repositories.receipt_aware_delivery_log_repository import ReceiptAwareDeliveryLogRepository
from app.services.receipt_aware_universal_notification_service import ReceiptAwareUniversalNotificationService


class _NotificationRepo:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        self.recorded = []

    def record_interest(self, request_id, buyer, seller):
        self.recorded.append((request_id, buyer, seller))
        return 1


class _WhatsApp:
    def __init__(self):
        self.calls = []
        self.counter = 0

    def _ok(self):
        self.counter += 1
        return {"success": True, "provider_message_id": f"wamid.{self.counter}", "status": "SENT_TO_PROVIDER"}

    def send_reply_buttons(self, mobile, body, buttons):
        self.calls.append(("buttons", str(mobile), str(body)))
        return self._ok()

    def send_text_message(self, mobile, body):
        self.calls.append(("text", str(mobile), str(body)))
        return self._ok()


def _contact(user_id):
    return {"mobile": str(user_id), "name": str(user_id)}


def test_async_failed_interactive_receipt_retries_plain_text(tmp_path):
    wa = _WhatsApp()
    repo = _NotificationRepo(tmp_path / "podx.db")
    service = ReceiptAwareUniversalNotificationService(repo, wa, _contact)
    request = {"id": 91, "user_id": "buyer", "side": "NEED", "subject": "chicken", "quantity": 5, "unit": "kg"}

    result = service.register_interest(request, "buyer", "seller")
    assert result["status"] == "WAITING_SELLER_CONFIRM"
    assert wa.calls[0][0] == "buttons"

    retry = service.handle_delivery_status("wamid.1", "failed", "interactive delivery failed")
    assert retry["status"] == "FALLBACK_SENT"
    assert wa.calls[-1][0] == "text"
    assert wa.calls[-1][1] == "seller"
    assert "CONFIRM" in wa.calls[-1][2]
    assert "DECLINE" in wa.calls[-1][2]

    tracked = service.seller_delivery_receipts.by_provider_message_id("wamid.2")
    assert tracked["channel"] == "text_fallback"
    assert tracked["retry_count"] == 1


def test_failed_fallback_receipt_warns_buyer_once(tmp_path):
    wa = _WhatsApp()
    repo = _NotificationRepo(tmp_path / "podx.db")
    service = ReceiptAwareUniversalNotificationService(repo, wa, _contact)
    request = {"id": 92, "user_id": "buyer", "side": "NEED", "subject": "chicken"}

    service.register_interest(request, "buyer", "seller")
    service.handle_delivery_status("wamid.1", "failed", "interactive failed")
    final = service.handle_delivery_status("wamid.2", "failed", "text failed")

    assert final["status"] == "FINAL_DELIVERY_FAILED"
    assert wa.calls[-1][0] == "text"
    assert wa.calls[-1][1] == "buyer"
    assert "Seller WhatsApp delivery" in wa.calls[-1][2]


class _Database:
    def __init__(self):
        self.saved = []

    def execute(self, sql, args):
        self.saved.append(tuple(args))


def test_delivery_log_forwards_receipt_after_persisting():
    database = _Database()
    forwarded = []
    repo = ReceiptAwareDeliveryLogRepository(database, lambda **kwargs: forwarded.append(kwargs))

    repo.save_status("wamid.9", "919999999999", "failed", "provider error")

    assert database.saved
    assert forwarded == [{
        "provider_message_id": "wamid.9",
        "status": "failed",
        "error_message": "provider error",
    }]
