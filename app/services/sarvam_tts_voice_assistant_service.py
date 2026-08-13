from __future__ import annotations

import base64
import io
import wave
from typing import Any, Optional

import httpx

from app.services.sarvam_primary_voice_assistant_service import SarvamPrimaryVoiceAssistantService


class SarvamTTSVoiceAssistantService(SarvamPrimaryVoiceAssistantService):
    """Use Sarvam Bulbul v3 for TTS with a strict latency budget.

    Gemini remains a compatibility fallback only for configuration/language cases.
    Runtime Sarvam timeout/provider failures fail fast so a late voice response never
    blocks or arrives tens of seconds after the already-delivered useful text reply.
    """

    TTS_URL = "https://api.sarvam.ai/text-to-speech"
    TTS_MODEL = "bulbul:v3"
    TTS_SPEAKER = "shubh"
    TTS_TIMEOUT_SECONDS = 3.5

    GEMINI_COMPATIBILITY_FALLBACK_STATUSES = {
        "SARVAM_TTS_NOT_CONFIGURED",
        "SARVAM_TTS_UNSUPPORTED_LANGUAGE",
    }

    SCRIPT_LANGUAGES = (
        (0x0980, 0x09FF, "bn-IN"),
        (0x0A00, 0x0A7F, "pa-IN"),
        (0x0A80, 0x0AFF, "gu-IN"),
        (0x0B00, 0x0B7F, "od-IN"),
        (0x0B80, 0x0BFF, "ta-IN"),
        (0x0C00, 0x0C7F, "te-IN"),
        (0x0C80, 0x0CFF, "kn-IN"),
        (0x0D00, 0x0D7F, "ml-IN"),
        (0x0900, 0x097F, "hi-IN"),
    )

    def synthesize(self, text: str) -> dict[str, Any]:
        primary = self._synthesize_sarvam(text)
        if primary.get("success"):
            return primary

        status = str(primary.get("status") or "SARVAM_TTS_ERROR")
        if status not in self.GEMINI_COMPATIBILITY_FALLBACK_STATUSES:
            print(
                "VOICE TTS PATH: stage=sarvam_tts_fast_fail "
                f"status={status} error_type={primary.get('error_type')} "
                "gemini_fallback=False",
                flush=True,
            )
            failed = dict(primary)
            failed["tts_path"] = "sarvam_fast_fail"
            failed["gemini_fallback"] = False
            return failed

        print(
            "VOICE TTS PATH: stage=sarvam_tts_compatibility_fallback "
            f"status={status} error_type={primary.get('error_type')}",
            flush=True,
        )
        fallback = super().synthesize(text)
        fallback["tts_path"] = "gemini_compatibility_fallback"
        fallback["sarvam_tts_status"] = status
        fallback["gemini_fallback"] = True
        return fallback

    def _synthesize_sarvam(self, text: str) -> dict[str, Any]:
        if not self.sarvam_api_key:
            return {"success": False, "status": "SARVAM_TTS_NOT_CONFIGURED"}

        spoken_text = self.prepare_spoken_text(text)
        if not spoken_text:
            return {"success": False, "status": "EMPTY_TTS_TEXT"}

        language_code = self.detect_tts_language(spoken_text)
        if not language_code:
            return {"success": False, "status": "SARVAM_TTS_UNSUPPORTED_LANGUAGE"}

        cache_key = f"sarvam:{language_code}:{spoken_text}"
        cached_pcm = self._tts_cache.get(cache_key)
        if cached_pcm:
            return self._success_result(
                cached_pcm,
                spoken_text,
                language_code,
                sample_rate=24000,
                channels=1,
                cache_hit=True,
            )

        header_name = "api-" + "subscription-key"
        headers = {header_name: self.sarvam_api_key, "Content-Type": "application/json"}
        payload = {
            "text": spoken_text,
            "target_language_code": language_code,
            "speaker": self.TTS_SPEAKER,
            "model": self.TTS_MODEL,
            "pace": 1.1,
            "speech_sample_rate": 24000,
            "output_audio_codec": "wav",
            "temperature": 0.4,
        }

        try:
            with httpx.Client(timeout=self.TTS_TIMEOUT_SECONDS) as client:
                response = client.post(self.TTS_URL, headers=headers, json=payload)
            if response.status_code != 200:
                return {
                    "success": False,
                    "status": f"SARVAM_TTS_HTTP_{response.status_code}",
                    "error_type": "HTTPStatusError",
                }

            body = response.json()
            audio_items = body.get("audios") or []
            if not audio_items:
                return {"success": False, "status": "SARVAM_TTS_EMPTY_AUDIO"}

            wav_bytes = base64.b64decode(str(audio_items[0]))
            pcm_bytes, sample_rate, channels = self.wav_to_pcm(wav_bytes)
            if not pcm_bytes:
                return {"success": False, "status": "SARVAM_TTS_EMPTY_PCM"}

            self._cache_tts(cache_key, pcm_bytes)
            print(
                "VOICE TTS PATH: stage=sarvam_tts success=True "
                f"language={language_code} pcm_bytes={len(pcm_bytes)}",
                flush=True,
            )
            return self._success_result(
                pcm_bytes,
                spoken_text,
                language_code,
                sample_rate=sample_rate,
                channels=channels,
                cache_hit=False,
            )
        except httpx.TimeoutException as error:
            return {
                "success": False,
                "status": "SARVAM_TTS_TIMEOUT",
                "error_type": type(error).__name__,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "SARVAM_TTS_ERROR",
                "error_type": type(error).__name__,
                "error": str(error)[:300],
            }

    def _success_result(
        self,
        pcm_bytes: bytes,
        spoken_text: str,
        language_code: str,
        *,
        sample_rate: int,
        channels: int,
        cache_hit: bool,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "status": "SYNTHESIZED_SARVAM_CACHE" if cache_hit else "SYNTHESIZED_SARVAM",
            "content": pcm_bytes,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": 2,
            "spoken_text": spoken_text,
            "model": self.TTS_MODEL,
            "voice": self.TTS_SPEAKER,
            "cache_hit": cache_hit,
            "tts_path": "sarvam_bulbul_v3",
            "language_code": language_code,
        }

    @staticmethod
    def wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int]:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            if int(wav_file.getsampwidth()) != 2:
                raise ValueError("Sarvam WAV must be signed 16-bit PCM")
            sample_rate = int(wav_file.getframerate())
            channels = int(wav_file.getnchannels())
            pcm_bytes = wav_file.readframes(wav_file.getnframes())
        return pcm_bytes, sample_rate, channels

    @classmethod
    def detect_tts_language(cls, text: str) -> Optional[str]:
        clean = str(text or "")
        for character in clean:
            codepoint = ord(character)
            for start, end, language_code in cls.SCRIPT_LANGUAGES:
                if start <= codepoint <= end:
                    return language_code
        if any("a" <= character.lower() <= "z" for character in clean):
            return "en-IN"
        return None
