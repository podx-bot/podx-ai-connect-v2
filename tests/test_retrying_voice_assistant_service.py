from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService
from app.services.voice_assistant_service import VoiceAssistantService


def test_retries_transient_transcription_failure(monkeypatch):
    calls = []

    def fake_transcribe(self, audio_bytes, mime_type):
        calls.append(1)
        if len(calls) == 1:
            return {"success": False, "status": "EMPTY_TRANSCRIPT"}
        return {"success": True, "status": "TRANSCRIBED", "transcript": "Salon appointment కావాలి"}

    monkeypatch.setattr(VoiceAssistantService, "transcribe", fake_transcribe)
    service = RetryingVoiceAssistantService(api_key="test", transcription_attempts=2)

    result = service.transcribe(b"audio", "audio/ogg")

    assert result["success"] is True
    assert result["status"] == "TRANSCRIBED_RETRY"
    assert result["attempts"] == 2
    assert len(calls) == 2


def test_does_not_retry_non_transient_failure(monkeypatch):
    calls = []

    def fake_transcribe(self, audio_bytes, mime_type):
        calls.append(1)
        return {"success": False, "status": "AUDIO_TOO_LARGE"}

    monkeypatch.setattr(VoiceAssistantService, "transcribe", fake_transcribe)
    service = RetryingVoiceAssistantService(api_key="test", transcription_attempts=2)

    result = service.transcribe(b"audio", "audio/ogg")

    assert result["success"] is False
    assert result["status"] == "AUDIO_TOO_LARGE"
    assert result["attempts"] == 1
    assert len(calls) == 1
