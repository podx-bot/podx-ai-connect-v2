from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService
from app.services.voice_assistant_service import VoiceAssistantService


class FakeCodec:
    def audio_to_wav(self, audio_bytes):
        return {"success": True, "status": "NORMALIZED", "content": b"wav"}


class FailingCodec:
    def audio_to_wav(self, audio_bytes):
        return {"success": False, "status": "FFMPEG_NORMALIZE_ERROR"}


def test_normalized_generate_content_is_primary_path(monkeypatch):
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
        generate_content_attempts=1,
    )
    calls = []

    def fake_generate_content(audio_bytes, mime_type):
        calls.append((audio_bytes, mime_type))
        return {
            "success": True,
            "status": "TRANSCRIBED_GENERATE_CONTENT",
            "transcript": "Hi PODX నాకు Electrician కావాలి",
        }

    monkeypatch.setattr(service, "_transcribe_generate_content", fake_generate_content)

    result = service.transcribe(b"ogg", "audio/ogg; codecs=opus")

    assert calls == [(b"wav", "audio/wav")]
    assert result["success"] is True
    assert result["transcription_path"] == "normalized_generate_content"
    assert result["transcript"].startswith("Hi PODX")
    assert result["fallback_chain"][0]["status"] == "NORMALIZED"


def test_original_audio_is_used_when_normalized_generate_content_fails(monkeypatch):
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
        generate_content_attempts=1,
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

    result = service.transcribe(b"ogg", "audio/ogg; codecs=opus")

    assert calls == [(b"wav", "audio/wav"), (b"ogg", "audio/ogg")]
    assert result["success"] is True
    assert result["transcript"] == "4:30 PM"
    assert result["transcription_path"] == "original_generate_content"
    assert result["secondary_original_fallback"] is True


def test_generate_content_transient_failure_retries_before_fallback(monkeypatch):
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
        generate_content_attempts=2,
        generate_content_retry_delay_seconds=0,
    )
    attempts = []

    def fake_generate_content(audio_bytes, mime_type):
        attempts.append((audio_bytes, mime_type))
        if len(attempts) == 1:
            return {"success": False, "status": "GENERATE_CONTENT_TRANSCRIPTION_ERROR"}
        return {
            "success": True,
            "status": "TRANSCRIBED_GENERATE_CONTENT",
            "transcript": "Chicken రెండు కేజీలు కావాలి",
        }

    monkeypatch.setattr(service, "_transcribe_generate_content", fake_generate_content)

    result = service.transcribe(b"ogg", "audio/ogg")

    assert attempts == [(b"wav", "audio/wav"), (b"wav", "audio/wav")]
    assert result["success"] is True
    assert result["attempts"] == 2
    assert result["transcription_path"] == "normalized_generate_content"


def test_interactions_path_is_last_resort(monkeypatch):
    def succeed_direct(self, audio_bytes, mime_type):
        return {
            "success": True,
            "status": "TRANSCRIBED",
            "transcript": "Electrician కావాలి",
        }

    monkeypatch.setattr(VoiceAssistantService, "transcribe", succeed_direct)
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FailingCodec(),
        transcription_attempts=1,
        generate_content_attempts=1,
    )
    monkeypatch.setattr(
        service,
        "_transcribe_generate_content",
        lambda audio_bytes, mime_type: {
            "success": False,
            "status": "GENERATE_CONTENT_TRANSCRIPTION_ERROR",
        },
    )

    result = service.transcribe(b"ogg", "audio/ogg")

    assert result["success"] is True
    assert result["transcription_path"] == "interactions_last_resort"
    assert result["fallback_chain"][-1]["success"] is True
