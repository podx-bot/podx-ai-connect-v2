from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService
from app.services.voice_assistant_service import VoiceAssistantService


class FakeCodec:
    def audio_to_wav(self, audio_bytes):
        return {"success": True, "status": "NORMALIZED", "content": b"wav"}


def test_normalized_fallback_is_used_after_direct_failure(monkeypatch):
    def fail_direct(self, audio_bytes, mime_type):
        return {"success": False, "status": "EMPTY_TRANSCRIPT"}

    monkeypatch.setattr(VoiceAssistantService, "transcribe", fail_direct)
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
    )
    monkeypatch.setattr(
        service,
        "_transcribe_generate_content",
        lambda audio_bytes, mime_type: {
            "success": True,
            "status": "TRANSCRIBED_GENERATE_CONTENT",
            "transcript": "Salon appointment today 9 PM nearby",
        },
    )

    result = service.transcribe(b"ogg", "audio/ogg")

    assert result["success"] is True
    assert result["normalized_fallback"] is True
    assert result["transcript"].endswith("nearby")


def test_original_audio_is_retried_when_normalized_generate_content_fails(monkeypatch):
    def fail_direct(self, audio_bytes, mime_type):
        return {"success": False, "status": "EMPTY_TRANSCRIPT"}

    monkeypatch.setattr(VoiceAssistantService, "transcribe", fail_direct)
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
    )
    calls = []

    def fake_generate_content(audio_bytes, mime_type):
        calls.append((audio_bytes, mime_type))
        if mime_type == "audio/wav":
            return {"success": False, "status": "EMPTY_GENERATE_CONTENT_TRANSCRIPT"}
        return {
            "success": True,
            "status": "TRANSCRIBED_GENERATE_CONTENT",
            "transcript": "4:30 PM",
        }

    monkeypatch.setattr(service, "_transcribe_generate_content", fake_generate_content)

    result = service.transcribe(b"ogg", "audio/ogg")

    assert calls == [(b"wav", "audio/wav"), (b"ogg", "audio/ogg")]
    assert result["success"] is True
    assert result["transcript"] == "4:30 PM"
    assert result["secondary_original_fallback"] is True
    assert result["normalized_status"] == "EMPTY_GENERATE_CONTENT_TRANSCRIPT"
