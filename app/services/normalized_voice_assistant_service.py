from typing import Any, Optional

from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


class NormalizedVoiceAssistantService(RetryingVoiceAssistantService):
    """Retry voice transcription with a normalized WAV fallback for WhatsApp OGG/Opus."""

    def __init__(self, *args, audio_codec_service=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.audio_codec_service = audio_codec_service

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        result = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
        if result.get("success"):
            return result
        if self.audio_codec_service is None:
            return result

        normalized = self.audio_codec_service.audio_to_wav(audio_bytes)
        if not normalized.get("success"):
            result = dict(result)
            result["normalization_status"] = normalized.get("status")
            return result

        fallback = super().transcribe(
            audio_bytes=normalized["content"],
            mime_type="audio/wav",
        )
        fallback = dict(fallback)
        fallback["normalized_fallback"] = True
        return fallback
