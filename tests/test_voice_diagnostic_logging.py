from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService
from app.services.voice_assistant_service import VoiceAssistantService


class FakeCodec:
    def audio_to_wav(self, audio_bytes):
        return {"success": True, "status": "NORMALIZED", "content": b"wav"}


def test_voice_pipeline_logs_each_failed_stage_without_audio_content(monkeypatch, capsys):
    def fail_direct(self, audio_bytes, mime_type):
        return {"success": False, "status": "EMPTY_TRANSCRIPT", "http_status": 200}

    monkeypatch.setattr(VoiceAssistantService, "transcribe", fail_direct)
    service = NormalizedVoiceAssistantService(
        api_key="test",
        audio_codec_service=FakeCodec(),
        transcription_attempts=1,
    )

    calls = []

    def fail_generate_content(audio_bytes, mime_type):
        calls.append((audio_bytes, mime_type))
        return {
            "success": False,
            "status": "EMPTY_GENERATE_CONTENT_TRANSCRIPT",
        }

    monkeypatch.setattr(service, "_transcribe_generate_content", fail_generate_content)

    result = service.transcribe(b"secret-audio", "audio/ogg")
    output = capsys.readouterr().out

    assert result["success"] is False
    assert calls == [(b"wav", "audio/wav"), (b"secret-audio", "audio/ogg")]
    assert "stage=direct" in output
    assert "status=EMPTY_TRANSCRIPT" in output
    assert "stage=normalize" in output
    assert "status=NORMALIZED" in output
    assert "stage=normalized_generate_content" in output
    assert "stage=original_generate_content_after_wav" in output
    assert "secret-audio" not in output
