from pathlib import Path


def test_legacy_webhook_wires_recovery_notices():
    text = Path("app/api/routes/webhook.py").read_text(encoding="utf-8")
    assert 'WebhookRecoveryService' in text
    assert '_recover_user(container, incoming.sender_mobile, "audio")' in text
    assert '_recover_user(container, incoming.sender_mobile, "location")' in text


def test_fast_webhook_wires_all_media_recovery_notices():
    text = Path("app/api/routes/fast_webhook.py").read_text(encoding="utf-8")
    assert 'WebhookRecoveryService' in text
    assert '_recover(container, incoming, "audio")' in text
    assert '_recover(container, incoming, "image")' in text
    assert '_recover(container, incoming, "document")' in text
