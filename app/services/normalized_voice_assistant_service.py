import time
from typing import Any, Optional

from google import genai
from google.genai import types

from app.services.retrying_voice_assistant_service import RetryingVoiceAssistantService


def _voice_diag(message: str) -> None:
    print(f"VOICE TRANSCRIPTION PATH: {message}", flush=True)


class NormalizedVoiceAssistantService(RetryingVoiceAssistantService):
    """Production voice transcription with normalized-audio primary path and fallbacks."""

    RETRYABLE_GENERATE_CONTENT_STATUSES = {
        "EMPTY_GENERATE_CONTENT_TRANSCRIPT",
        "GENERATE_CONTENT_TRANSCRIPTION_ERROR",
    }

    def __init__(
        self,
        *args,
        audio_codec_service=None,
        generate_content_attempts: int = 1,
        generate_content_retry_delay_seconds: float = 0.2,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.audio_codec_service = audio_codec_service
        self.generate_content_attempts = max(1, int(generate_content_attempts))
        self.generate_content_retry_delay_seconds = max(
            0.0, float(generate_content_retry_delay_seconds)
        )
        self._genai_client = genai.Client(api_key=self.api_key) if self.api_key else None

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}
        if len(audio_bytes) > self.max_audio_bytes:
            return {
                "success": False,
                "status": "AUDIO_TOO_LARGE",
                "max_bytes": self.max_audio_bytes,
                "actual_bytes": len(audio_bytes),
            }

        original_mime_type = self._normalize_mime_type(mime_type)
        fallback_chain: list[dict[str, Any]] = []

        # Primary path: normalize WhatsApp OGG/Opus to mono 16 kHz WAV, then
        # transcribe with Gemini generateContent using inline audio bytes.
        normalized = None
        if self.audio_codec_service is not None:
            normalized = self.audio_codec_service.audio_to_wav(audio_bytes)
            fallback_chain.append(
                {
                    "stage": "normalize",
                    "success": bool(normalized.get("success")),
                    "status": normalized.get("status"),
                }
            )
            _voice_diag(
                f"stage=normalize success={bool(normalized.get('success'))} "
                f"status={normalized.get('status')} "
                f"wav_bytes={len(normalized.get('content') or b'')}"
            )
        else:
            fallback_chain.append(
                {"stage": "normalize", "success": False, "status": "NO_CODEC"}
            )
            _voice_diag("stage=normalize success=False status=NO_CODEC")

        if normalized and normalized.get("success"):
            normalized_result = self._transcribe_generate_content_with_retry(
                audio_bytes=normalized["content"],
                mime_type="audio/wav",
            )
            fallback_chain.append(
                {
                    "stage": "normalized_generate_content",
                    "success": bool(normalized_result.get("success")),
                    "status": normalized_result.get("status"),
                    "attempts": normalized_result.get("attempts", 1),
                }
            )
            _voice_diag(
                "stage=normalized_generate_content "
                f"success={bool(normalized_result.get('success'))} "
                f"status={normalized_result.get('status')} "
                f"attempts={normalized_result.get('attempts', 1)}"
            )
            if normalized_result.get("success"):
                result = dict(normalized_result)
                result["transcription_path"] = "normalized_generate_content"
                result["normalized_fallback"] = True
                result["fallback_chain"] = fallback_chain
                return result

        # Secondary path: transcribe original WhatsApp audio directly. This keeps
        # voice working even when ffmpeg normalization is unavailable or fails.
        original_result = self._transcribe_generate_content_with_retry(
            audio_bytes=audio_bytes,
            mime_type=original_mime_type,
        )
        fallback_chain.append(
            {
                "stage": "original_generate_content",
                "success": bool(original_result.get("success")),
                "status": original_result.get("status"),
                "attempts": original_result.get("attempts", 1),
            }
        )
        _voice_diag(
            "stage=original_generate_content "
            f"success={bool(original_result.get('success'))} "
            f"status={original_result.get('status')} "
            f"attempts={original_result.get('attempts', 1)}"
        )
        if original_result.get("success"):
            result = dict(original_result)
            result["transcription_path"] = "original_generate_content"
            result["normalized_fallback"] = False
            result["secondary_original_fallback"] = True
            result["fallback_chain"] = fallback_chain
            return result

        # Last resort: retain the older Interactions API path. The parent retry
        # service applies its own transient retry policy here.
        direct = super().transcribe(
            audio_bytes=audio_bytes,
            mime_type=original_mime_type,
        )
        fallback_chain.append(
            {
                "stage": "interactions_last_resort",
                "success": bool(direct.get("success")),
                "status": direct.get("status"),
                "attempts": direct.get("attempts", 1),
            }
        )
        _voice_diag(
            f"stage=interactions_last_resort success={bool(direct.get('success'))} "
            f"status={direct.get('status')} attempts={direct.get('attempts', 1)} "
            f"bytes={len(audio_bytes)} mime={original_mime_type}"
        )
        if direct.get("success"):
            result = dict(direct)
            result["transcription_path"] = "interactions_last_resort"
            result["fallback_chain"] = fallback_chain
            return result

        return {
            "success": False,
            "status": "VOICE_TRANSCRIPTION_EXHAUSTED",
            "model": self.model,
            "mime_type": original_mime_type,
            "actual_bytes": len(audio_bytes),
            "fallback_chain": fallback_chain,
            "last_status": direct.get("status"),
        }

    def _transcribe_generate_content_with_retry(
        self,
        audio_bytes: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        last_result: dict[str, Any] | None = None
        for attempt in range(1, self.generate_content_attempts + 1):
            result = dict(
                self._transcribe_generate_content(
                    audio_bytes=audio_bytes,
                    mime_type=mime_type,
                )
            )
            result["attempts"] = attempt
            if result.get("success"):
                return result
            last_result = result
            if result.get("status") not in self.RETRYABLE_GENERATE_CONTENT_STATUSES:
                return result
            if (
                attempt < self.generate_content_attempts
                and self.generate_content_retry_delay_seconds
            ):
                time.sleep(self.generate_content_retry_delay_seconds * attempt)
        return last_result or {
            "success": False,
            "status": "GENERATE_CONTENT_TRANSCRIPTION_FAILED",
            "attempts": self.generate_content_attempts,
        }

    def _transcribe_generate_content(
        self,
        audio_bytes: bytes,
        mime_type: str,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}

        prompt = (
            "This is a WhatsApp voice note from an Indian user. Telugu is the primary expected language. "
            "Accurately transcribe every audible spoken word. The utterance may be very short, including one word, "
            "a number, yes/no, a time, or a request beginning with 'Hi PODX'. Do not treat short speech as silence. "
            "If Telugu is spoken, write Telugu in Telugu script. Preserve clear English words naturally when mixed "
            "with Telugu, including PODX, Electrician, Chicken, Doctor, Today, Tomorrow, AM and PM. "
            "Also support Hindi or English when actually spoken. Preserve the user's meaning exactly. "
            "Do not translate, explain, summarize, correct, infer missing words, or add labels. "
            "Return only the transcription text."
        )
        try:
            client = self._genai_client or genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type=mime_type,
                    ),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=256,
                ),
            )
            transcript = self._clean_transcript(
                str(getattr(response, "text", "") or "")
            )
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
                "error_type": type(error).__name__,
                "error": str(error)[:500],
                "model": self.model,
            }

    @staticmethod
    def _clean_transcript(value: str) -> str:
        transcript = str(value or "").strip().strip('"').strip("`").strip()
        lowered = transcript.lower()
        for prefix in ("transcript:", "transcription:"):
            if lowered.startswith(prefix):
                transcript = transcript[len(prefix):].strip()
                break
        return " ".join(transcript.split())
