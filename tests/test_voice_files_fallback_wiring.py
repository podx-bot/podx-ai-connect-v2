from pathlib import Path

from app.services.files_fallback_voice_assistant_service import FilesFallbackVoiceAssistantService


def test_container_uses_files_fallback_voice_service():
    source = Path("app/core/container.py").read_text(encoding="utf-8")
    assert "FilesFallbackVoiceAssistantService" in source
    assert "self.voice_assistant_service = FilesFallbackVoiceAssistantService(" in source


def test_files_fallback_audio_suffix_mapping():
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/wav") == ".wav"
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/ogg") == ".ogg"
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/mpeg") == ".mp3"
