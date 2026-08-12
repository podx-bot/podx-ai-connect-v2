from typing import Any, Optional

from google import genai
from google.genai import types

from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


def _voice_diag(message: str) -> None:
    print(f"VOICE TRANSCRIPTION PATH: {message}", flush=True)


class NormalizedVoiceAssistantService(RetryingVoiceAssistantService):
    """Fast voice transcription with normalized WAV + generateContent fallbacks."""

    def __init__(self, *args, audio_codec_service=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.audio_codec_service = audio_codec_service

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        direct = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
        _voice_diag(
            f"stage=direct success={bool(direct.get('success'))} "
            f"status={direct.get('status')} http={direct.get('http_status')} "
            f"bytes={len(audio_bytes or b'')} mime={mime_type}"
        )
        if direct.get("success"):
            return direct

        original_mime_type = self._normalize_mime_type(mime_type)
        normalized = None
        if self.audio_codec_service is not None:
            normalized = self.audio_codec_service.audio_to_wav(audio_bytes)
            _voice_diag(
                f"stage=normalize success={bool(normalized.get('success'))} "
                f"status={normalized.get('status')} "
                f"wav_bytes={len(normalized.get('content') or b'')}"
            )
        else:
            _voice_diag("stage=normalize success=False status=NO_CODEC")

        if normalized and normalized.get("success"):
            normalized_fallback = self._transcribe_generate_content(
                audio_bytes=normalized["content"],
                mime_type="audio/wav",
            )
            _voice_diag(
                f"stage=normalized_generate_content success={bool(normalized_fallback.get('success'))} "
                f"status={normalized_fallback.get('status')} "
                f"error={normalized_fallback.get('error')}"
            )
            if normalized_fallback.get("success"):
                result = dict(normalized_fallback)
                result["normalized_fallback"] = True
                result["direct_status"] = direct.get("status")
                return result

            original_fallback = self._transcribe_generate_content(
                audio_bytes=audio_bytes,
                mime_type=original_mime_type,
            )
            _voice_diag(
                f"stage=original_generate_content_after_wav success={bool(original_fallback.get('success'))} "
                f"status={original_fallback.get('status')} "
                f"error={original_fallback.get('error')}"
            )
            result = dict(original_fallback)
            result["normalized_fallback"] = False
            result["secondary_original_fallback"] = True
            result["direct_status"] = direct.get("status")
            result["normalized_status"] = normalized_fallback.get("status")
            return result

        fallback = self._transcribe_generate_content(
            audio_bytes=audio_bytes,
            mime_type=original_mime_type,
        )
        _voice_diag(
            f"stage=original_generate_content_no_wav success={bool(fallback.get('success'))} "
            f"status={fallback.get('status')} error={fallback.get('error')}"
        )
        result = dict(fallback)
        result["normalized_fallback"] = False
        result["direct_status"] = direct.get("status")
        if normalized:
            result["normalization_status"] = normalized.get("status")
        return result

    def _transcribe_generate_content(self, audio_bytes: bytes, mime_type: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}

        prompt = (
            "This is a WhatsApp voice note from an Indian user. Telugu is the primary expected language. "
            "Accurately transcribe every audible spoken word. The utterance may be extremely short, including only one word, a number, yes/no, or a time such as 4:30 PM. "
            "Do not treat a short utterance as silence when speech is audible. "
            "If the speaker uses Telugu, write the transcript in Telugu script. "
            "If the speaker mixes Telugu with English words such as Salon, Doctor, Today, Tomorrow, AM or PM, preserve those clear English words naturally. "
            "Also support Hindi or English when they are actually spoken. Preserve the user's exact meaning. "
            "Do not translate, explain, summarize, correct the request, infer missing words, or add labels. "
            "Return only the transcription text."
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
                "language_policy": "telugu_first_preserve_input",
            }
        except Exception as error:
            return {
                "success": False,
                "status": "GENERATE_CONTENT_TRANSCRIPTION_ERROR",
                "error": str(error),
                "model": self.model,
            }
