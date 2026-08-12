from typing import Any, Optional

from google import genai
from google.genai import types

from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


class NormalizedVoiceAssistantService(RetryingVoiceAssistantService):
    """Fast voice transcription with normalized WAV + generateContent fallback."""

    def __init__(self, *args, audio_codec_service=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.audio_codec_service = audio_codec_service

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        # First try the current Interactions path. Keep this to one attempt in
        # production so a bad voice note does not make the user wait through
        # repeated identical API calls.
        direct = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
        if direct.get("success"):
            return direct

        normalized = None
        if self.audio_codec_service is not None:
            normalized = self.audio_codec_service.audio_to_wav(audio_bytes)

        # Use normalized mono 16 kHz WAV when ffmpeg can decode the WhatsApp
        # OGG/Opus note. generateContent accepts inline audio bytes and gives us
        # an independent fallback API path from Interactions.
        if normalized and normalized.get("success"):
            fallback = self._transcribe_generate_content(
                audio_bytes=normalized["content"],
                mime_type="audio/wav",
            )
            fallback = dict(fallback)
            fallback["normalized_fallback"] = True
            fallback["direct_status"] = direct.get("status")
            return fallback

        # If normalization itself fails, still try the original bytes through
        # generateContent before returning the user-facing failure.
        fallback = self._transcribe_generate_content(
            audio_bytes=audio_bytes,
            mime_type=self._normalize_mime_type(mime_type),
        )
        fallback = dict(fallback)
        fallback["normalized_fallback"] = False
        fallback["direct_status"] = direct.get("status")
        if normalized:
            fallback["normalization_status"] = normalized.get("status")
        return fallback

    def _transcribe_generate_content(self, audio_bytes: bytes, mime_type: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}

        prompt = (
            "Transcribe only the spoken words in this WhatsApp voice note. "
            "The speaker may use Telugu, English, Hindi, or mixed speech. "
            "Preserve the exact meaning and language. Do not translate, explain, "
            "summarize, or add labels. Return only the transcription text."
        )
        try:
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                ],
            )
            transcript = str(getattr(response, "text", "") or "").strip().strip('"')
            if not transcript:
                return {
                    "success": False,
                    "status": "EMPTY_GENERATE_CONTENT_TRANSCRIPT",
                    "model": self.model,
                }
            return {
                "success": True,
                "status": "TRANSCRIBED_GENERATE_CONTENT",
                "transcript": transcript,
                "mime_type": mime_type,
                "model": self.model,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "GENERATE_CONTENT_TRANSCRIPTION_ERROR",
                "error": str(error),
                "model": self.model,
            }
