import os
import tempfile
from typing import Any, Optional

from google.genai import types

from app.services.normalized_voice_assistant_service import NormalizedVoiceAssistantService, _voice_diag


class FilesFallbackVoiceAssistantService(NormalizedVoiceAssistantService):
    """Independent Gemini Files API fallback for WhatsApp voice notes."""

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        result = super().transcribe(audio_bytes=audio_bytes, mime_type=mime_type)
        if result.get("success"):
            return result

        effective_audio = audio_bytes
        effective_mime = self._normalize_mime_type(mime_type)
        normalization_status = "NOT_ATTEMPTED"

        if self.audio_codec_service is not None and audio_bytes:
            normalized = self.audio_codec_service.audio_to_wav(audio_bytes)
            normalization_status = str(normalized.get("status") or "UNKNOWN")
            if normalized.get("success") and normalized.get("content"):
                effective_audio = normalized["content"]
                effective_mime = "audio/wav"

        files_result = self._transcribe_files_api(effective_audio, effective_mime)
        _voice_diag(
            "stage=files_api_fallback "
            f"success={bool(files_result.get('success'))} "
            f"status={files_result.get('status')} "
            f"normalize_status={normalization_status} "
            f"bytes={len(effective_audio or b'')} mime={effective_mime}"
        )
        if files_result.get("success"):
            files_result["transcription_path"] = "files_api_fallback"
            files_result["previous_status"] = result.get("status")
            files_result["normalization_status"] = normalization_status
            return files_result

        exhausted = dict(result)
        exhausted["files_api_status"] = files_result.get("status")
        exhausted["files_api_error_type"] = files_result.get("error_type")
        exhausted["normalization_status"] = normalization_status
        return exhausted

    def _transcribe_files_api(self, audio_bytes: bytes, mime_type: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}

        prompt = (
            "Transcribe only the spoken words in this WhatsApp voice note. "
            "Telugu is the primary expected language, but English, Hindi and mixed speech are valid. "
            "Very short speech, one-word requests, numbers and phrases such as Hi PODX are valid speech. "
            "Preserve Telugu in Telugu script and clear English words naturally. "
            "Do not translate, summarize, explain, correct or infer missing words. "
            "Return only the transcription text."
        )

        client = self._genai_client
        uploaded = None
        local_path = None
        suffix = self._suffix_for_mime(mime_type)
        try:
            with tempfile.NamedTemporaryFile(prefix="podx_voice_", suffix=suffix, delete=False) as handle:
                handle.write(audio_bytes)
                local_path = handle.name

            uploaded = client.files.upload(
                file=local_path,
                config={"mime_type": mime_type, "display_name": "podx-whatsapp-voice"},
            )
            response = client.models.generate_content(
                model=self.model,
                contents=[prompt, uploaded],
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=256),
            )
            transcript = self._clean_transcript(str(getattr(response, "text", "") or ""))
            if not transcript:
                return {
                    "success": False,
                    "status": "EMPTY_FILES_API_TRANSCRIPT",
                    "model": self.model,
                }
            return {
                "success": True,
                "status": "TRANSCRIBED_FILES_API",
                "transcript": transcript,
                "mime_type": mime_type,
                "model": self.model,
                "language_policy": "telugu_first_preserve_input",
            }
        except Exception as error:
            return {
                "success": False,
                "status": "FILES_API_TRANSCRIPTION_ERROR",
                "error_type": type(error).__name__,
                "error": str(error)[:500],
                "model": self.model,
            }
        finally:
            try:
                if uploaded is not None and getattr(uploaded, "name", None):
                    client.files.delete(name=uploaded.name)
            except Exception as cleanup_error:
                _voice_diag(
                    "stage=files_api_cleanup success=False "
                    f"error_type={type(cleanup_error).__name__}"
                )
            if local_path:
                try:
                    os.unlink(local_path)
                except OSError:
                    pass

    @staticmethod
    def _suffix_for_mime(mime_type: str) -> str:
        mapping = {
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
        }
        return mapping.get(str(mime_type or "").lower(), ".audio")
