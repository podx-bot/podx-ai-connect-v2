from app.whatsapp.whatsapp_service import WhatsAppService


def _service():
    service = WhatsAppService("token", "phone", "v1")
    sent = []

    def fake_send(payload):
        sent.append(payload)
        return {"success": True, "status": "SENT_TO_PROVIDER", "attempts": 1}

    service._send_with_retry = fake_send
    return service, sent


def test_same_pending_status_is_suppressed_within_window():
    service, sent = _service()
    try:
        message = "⏳ chicken availability seller confirmation కోసం wait చేస్తున్నాను."
        first = service.send_text_message("919999999999", message)
        second = service.send_text_message("919999999999", message)

        assert first["success"] is True
        assert second["status"] == "DUPLICATE_STATUS_SUPPRESSED"
        assert second["suppressed"] is True
        assert len(sent) == 1
    finally:
        service.close()


def test_normal_customer_reply_is_not_suppressed():
    service, sent = _service()
    try:
        message = "సరే 👍 10 kg boneless chicken కోసం చూస్తున్నాను."
        service.send_text_message("919999999999", message)
        service.send_text_message("919999999999", message)
        assert len(sent) == 2
    finally:
        service.close()


def test_same_status_can_go_to_different_recipients():
    service, sent = _service()
    try:
        message = "availability confirmation pending"
        service.send_text_message("911111111111", message)
        service.send_text_message("922222222222", message)
        assert len(sent) == 2
    finally:
        service.close()
