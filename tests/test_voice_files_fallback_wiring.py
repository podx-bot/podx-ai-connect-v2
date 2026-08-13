from pathlib import Path

from app.services.files_fallback_voice_assistant_service import FilesFallbackVoiceAssistantService
from app.services.sarvam_primary_voice_assistant_service import SarvamPrimaryVoiceAssistantService


def test_container_uses_sarvam_primary_with_files_fallback_chain():
    source = Path("app/core/container.py").read_text(encoding="utf-8")
    assert "SarvamPrimaryVoiceAssistantService" in source
    assert "self.voice_assistant_service = SarvamPrimaryVoiceAssistantService(" in source
    assert issubclass(SarvamPrimaryVoiceAssistantService, FilesFallbackVoiceAssistantService)


def test_files_fallback_audio_suffix_mapping():
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/wav") == ".wav"
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/ogg") == ".ogg"
    assert FilesFallbackVoiceAssistantService._suffix_for_mime("audio/mpeg") == ".mp3"
