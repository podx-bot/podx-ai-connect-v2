from app.services.sarvam_tts_voice_assistant_service import SarvamTTSVoiceAssistantService


class _FakeStreamResponse:
    status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_bytes(self):
        yield b"OggS"
        yield b"direct-opus-audio"


class _FakePersistentClient:
    def __init__(self):
        self.calls = []

    def stream(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _FakeStreamResponse()


def test_tts_reuses_existing_sarvam_http_client():
    service = SarvamTTSVoiceAssistantService(
        api_key="test-key",
        sarvam_api_key="test-sarvam-key",
    )
    service._sarvam_http_client.close()
    fake_client = _FakePersistentClient()
    service._sarvam_http_client = fake_client

    result = service._synthesize_sarvam("మీకు సహాయం చేస్తాను")

    assert result["success"] is True
    assert result["content"] == b"OggSdirect-opus-audio"
    assert len(fake_client.calls) == 1
    method, url, kwargs = fake_client.calls[0]
    assert method == "POST"
    assert url == service.TTS_URL
    assert kwargs["timeout"].read == service.TTS_READ_TIMEOUT_SECONDS
