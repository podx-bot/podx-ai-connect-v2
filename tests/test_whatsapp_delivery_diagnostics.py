from app.services.receipt_aware_universal_notification_service import ReceiptAwareUniversalNotificationService
from app.whatsapp.payload_parser import extract_delivery_statuses


def test_delivery_status_normalizes_meta_error_fields():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": "wamid.failed",
                        "recipient_id": "919999999999",
                        "status": "failed",
                        "errors": [{
                            "code": 131026,
                            "title": "Message undeliverable",
                            "message": "Message undeliverable",
                            "error_data": {"details": "Unable to deliver message"},
                        }],
                    }]
                }
            }]
        }]
    }

    statuses = extract_delivery_statuses(payload)

    assert len(statuses) == 1
    status = statuses[0]
    assert status.recipient_mobile == "919999999999"
    assert status.status == "failed"
    assert "META_CODE=131026" in status.error_message
    assert "TITLE=Message undeliverable" in status.error_message
    assert "DETAILS=Unable to deliver message" in status.error_message


def test_meta_error_code_extraction_supports_normalized_and_legacy_payloads():
    assert ReceiptAwareUniversalNotificationService._meta_error_code("META_CODE=131026 | TITLE=x") == "131026"
    assert ReceiptAwareUniversalNotificationService._meta_error_code("{'code': 131026, 'title': 'x'}") == "131026"
    assert ReceiptAwareUniversalNotificationService._meta_error_code(None) == ""
