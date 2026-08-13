from __future__ import annotations

from typing import Any, Optional

import httpx

from app.services.files_fallback_voice_assistant_service import FilesFallbackVoiceAssistantService
from app.services.normalized_voice_assistant_service import _voice_diag


class SarvamPrimaryVoiceAssistantService(FilesFallbackVoiceAssistantService):
    """Use Sarvam Saaras v3 as fast India-first STT, then fall back to Gemini."""

    SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

    def __init__(
        self,
        *args,
        sarvam_api_key: str = "",
        sarvam_model: str = "saaras:v3",
        sarvam_timeout_seconds: float = 8.0,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.sarvam_api_key = str(sarvam_api_key or "").strip()
        self.sarvam_model = str(sarvam_model or "saaras:v3").strip()
        self.sarvam_timeout_seconds = max(float(sarvam_timeout_seconds or 8.0), 1.0)

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        sarvam_result = self._transcribe_sarvam(audio_bytes=audio_bytes, mime_type=mime_type)
        if sarvam_result.get("success"):
            return sarvam_result

        _voice_diag(
            "stage=sarvam_primary_fallback "
            f"status={sarvam_result.get('status')} "
            f"error_type={sarvam_result.get('error_type')}"
        )
        fallback = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
        fallback["sarvam_status"] = sarvam_result.get("status")
        fallback["sarvam_error_type"] = sarvam_result.get("error_type")
        return fallback

    def _transcribe_sarvam(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        if not self.sarvam_api_key:
            return {"success": False, "status": "SARVAM_NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "SARVAM_EMPTY_AUDIO"}

        effective_mime = self._normalize_mime_type(mime_type)
        filename = "podx_voice" + self._suffix_for_mime(effective_mime)
        headers = {"api-subscription-key": self.sarvam_api_key}
        files = {"file": (filename, audio_bytes, effective_mime)}
        data = {
            "model": self.sarvam_model,
            "mode": "transcribe",
            "language_code": "unknown",
        }

        try:
            with httpx.Client(timeout=self.sarvam_timeout_seconds) as client:
                response = client.post(
                    self.SARVAM_STT_URL,
                    headers=headers,
                    files=files,
                    data=data,
                )
            if response.status_code != 200:
                return {
                    "success": False,
                    "status": f"SARVAM_HTTP_{response.status_code}",
                    "error_type": "HTTPStatusError",
                    "error": response.text[:500],
                }

            payload = response.json()
            transcript = self._clean_transcript(str(payload.get("transcript") or ""))
            if not transcript:
                return {
                    "success": False,
                    "status": "SARVAM_EMPTY_TRANSCRIPT",
                    "language_code": payload.get("language_code"),
                }

            result = {
                "success": True,
                "status": "TRANSCRIBED_SARVAM",
                "transcript": transcript,
                "mime_type": effective_mime,
                "model": self.sarvam_model,
                "language_code": payload.get("language_code"),
                "language_probability": payload.get("language_probability"),
                "transcription_path": "sarvam_primary",
            }
            _voice_diag(
                "stage=sarvam_primary success=True "
                f"language={result.get('language_code')} bytes={len(audio_bytes)} mime={effective_mime}"
            )
            return result
        except httpx.TimeoutException as error:
            return {
                "success": False,
                "status": "SARVAM_TIMEOUT",
                "error_type": type(error).__name__,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "SARVAM_TRANSCRIPTION_ERROR",
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            }
