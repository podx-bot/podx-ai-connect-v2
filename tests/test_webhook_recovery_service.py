from app.services.webhook_recovery_service import WebhookRecoveryService


class FakeWhatsApp:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = []

    def send_text_message(self, recipient_mobile: str, message: str):
        self.calls.append((recipient_mobile, message))
        if self.fail:
            raise RuntimeError("transport down")
        return {"success": True, "id": "msg-1"}


def test_recovery_messages_are_specific():
    assert "Voice" in WebhookRecoveryService.message_for("audio")
    assert "Photo" in WebhookRecoveryService.message_for("image")
    assert "Document" in WebhookRecoveryService.message_for("document")
    assert "Location" in WebhookRecoveryService.message_for("location")


def test_unknown_kind_falls_back_to_text_notice():
    assert WebhookRecoveryService.message_for("unknown") == WebhookRecoveryService.message_for("text")


def test_recovery_send_is_best_effort_success():
    whatsapp = FakeWhatsApp()
    result = WebhookRecoveryService.send(whatsapp, "919999999999", "location")
    assert result["success"] is True
    assert whatsapp.calls


def test_recovery_send_failure_never_raises():
    whatsapp = FakeWhatsApp(fail=True)
    result = WebhookRecoveryService.send(whatsapp, "919999999999", "audio")
    assert result["success"] is False
    assert result["status"] == "RECOVERY_SEND_EXCEPTION"
