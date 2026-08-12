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
