from app.models.session import ConversationStep
from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService
from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


def test_normalized_voice_fallback(monkeypatch):
    calls = []

    def fake_transcribe(self, audio_bytes, mime_type):
        calls.append((audio_bytes, mime_type))
        if mime_type == "audio/wav":
            return {"success": True, "status": "TRANSCRIBED", "transcript": "Salon appointment today 9 PM nearby"}
        return {"success": False, "status": "EMPTY_TRANSCRIPT"}

    monkeypatch.setattr(RetryingVoiceAssistantService, "transcribe", fake_transcribe)

    class Codec:
        def audio_to_wav(self, audio_bytes):
            return {"success": True, "content": b"wav"}

    service = NormalizedVoiceAssistantService(api_key="x", audio_codec_service=Codec())
    result = service.transcribe(b"ogg", "audio/ogg")
    assert result["success"] is True
    assert result["normalized_fallback"] is True
    assert calls[-1][1] == "audio/wav"


def test_compact_schedule_parser():
    from app.services.appointment_service import AppointmentService
    assert AppointmentService._extract_schedule("Salon appointment today 9 PM nearby") == ("Today", "9 PM")
    assert AppointmentService._normalize_target("Salon appointment today 9 PM nearby") == "Nearby"
