from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService
from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


def test_normalized_voice_fallback(monkeypatch):
    calls = []

    def fake_direct(self, audio_bytes, mime_type):
        calls.append(("direct", audio_bytes, mime_type))
        return {"success": False, "status": "EMPTY_TRANSCRIPT"}

    monkeypatch.setattr(RetryingVoiceAssistantService, "transcribe", fake_direct)

    class Codec:
        def audio_to_wav(self, audio_bytes):
            return {"success": True, "content": b"wav"}

    service = NormalizedVoiceAssistantService(api_key="x", audio_codec_service=Codec())

    def fake_generate_content(audio_bytes, mime_type):
        calls.append(("fallback", audio_bytes, mime_type))
        return {
            "success": True,
            "status": "TRANSCRIBED_GENERATE_CONTENT",
            "transcript": "Salon appointment today 9 PM nearby",
        }

    monkeypatch.setattr(service, "_transcribe_generate_content", fake_generate_content)

    result = service.transcribe(b"ogg", "audio/ogg")

    assert result["success"] is True
    assert result["normalized_fallback"] is True
    assert calls[-1] == ("fallback", b"wav", "audio/wav")


def test_compact_schedule_parser():
    from app.services.appointment_service import AppointmentService

    assert AppointmentService._extract_schedule("Salon appointment today 9 PM nearby") == ("Today", "9 PM")
    assert AppointmentService._normalize_target("Salon appointment today 9 PM nearby") == "Nearby"
