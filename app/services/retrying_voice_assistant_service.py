from typing import Any, Optional

from app.services.voice_assistant_service import VoiceAssistantService


class RetryingVoiceAssistantService(VoiceAssistantService):
    """Retry transient Gemini transcription failures without changing normal behavior."""

    RETRYABLE_STATUSES = {
        "EMPTY_TRANSCRIPT",
        "GEMINI_TRANSCRIPTION_ERROR",
    }

    def __init__(self, *args, transcription_attempts: int = 2, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.transcription_attempts = max(1, int(transcription_attempts))

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        last_result: dict[str, Any] | None = None

        for attempt in range(1, self.transcription_attempts + 1):
            result = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
            result = dict(result)
            result["attempts"] = attempt

            if result.get("success"):
                if attempt > 1:
                    result["status"] = "TRANSCRIBED_RETRY"
                return result

            last_result = result
            if result.get("status") not in self.RETRYABLE_STATUSES:
                return result

        return last_result or {
            "success": False,
            "status": "TRANSCRIPTION_FAILED",
            "attempts": self.transcription_attempts,
        }
