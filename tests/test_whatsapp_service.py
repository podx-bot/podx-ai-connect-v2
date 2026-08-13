import httpx

from app.whatsapp.whatsapp_service import WhatsAppService


def build_service(max_attempts=3):
    return WhatsAppService(
        access_token="token",
        phone_number_id="123",
        api_version="v23.0",
        max_attempts=max_attempts,
        retry_delay_seconds=0,
    )


def test_not_configured_returns_without_attempt():
    service = WhatsAppService("", "", "", retry_delay_seconds=0)
    result = service.send_text_message("919999999999", "Hi")

    assert result["success"] is False
    assert result["status"] == "NOT_CONFIGURED"
    assert result["attempts"] == 0


def test_retries_temporary_failure_then_succeeds(monkeypatch):
    service = build_service()
    responses = [
        httpx.Response(503, json={"error": {"message": "busy"}}),
        httpx.Response(200, json={"messages": [{"id": "wamid.ok"}]}),
    ]

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(service._http_client, "post", fake_post)
    result = service.send_text_message("919999999999", "Hi")

    assert result["success"] is True
    assert result["attempts"] == 2
    assert result["provider_message_id"] == "wamid.ok"


def test_does_not_retry_permanent_http_error(monkeypatch):
    service = build_service()
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    monkeypatch.setattr(service._http_client, "post", fake_post)
    result = service.send_text_message("919999999999", "Hi")

    assert result["success"] is False
    assert result["http_status"] == 400
    assert result["attempts"] == 1
    assert calls["count"] == 1


def test_stops_after_max_attempts_on_timeout(monkeypatch):
    service = build_service(max_attempts=3)
    calls = {"count": 0}

    def fake_post(*args, **kwargs):
        calls["count"] += 1
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(service._http_client, "post", fake_post)
    result = service.send_text_message("919999999999", "Hi")

    assert result["success"] is False
    assert result["status"] == "TIMEOUT"
    assert result["attempts"] == 3
    assert calls["count"] == 3


def test_send_voice_bytes_uploads_then_sends_audio(monkeypatch):
    service = build_service()
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/media"):
            return httpx.Response(200, json={"id": "media-voice-1"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.voice.ok"}]})

    monkeypatch.setattr(service._http_client, "post", fake_post)
    result = service.send_voice_bytes(
        recipient_mobile="919999999999",
        audio_bytes=b"fake-ogg-opus",
    )

    assert result["success"] is True
    assert result["media_id"] == "media-voice-1"
    assert result["provider_message_id"] == "wamid.voice.ok"
    assert len(calls) == 2
    assert calls[0][0].endswith("/media")
    assert calls[1][1]["json"]["audio"]["voice"] is True
