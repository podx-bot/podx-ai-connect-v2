from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from app.services.sarvam_primary_voice_assistant_service import SarvamPrimaryVoiceAssistantService


class SarvamTTSVoiceAssistantService(SarvamPrimaryVoiceAssistantService):
    """Use Sarvam Bulbul v3 HTTP streaming TTS with bounded latency."""

    TTS_URL = "https://api.sarvam.ai/text-to-speech/stream"
    TTS_MODEL = "bulbul:v3"
    TTS_SPEAKER = "shubh"
    TTS_SAMPLE_RATE = 24000
    TTS_OUTPUT_CODEC = "opus"
    TTS_OUTPUT_BITRATE = "32k"
    TTS_CONNECT_TIMEOUT_SECONDS = 2.5
    TTS_READ_TIMEOUT_SECONDS = 6.0
    TTS_MAX_AUDIO_BYTES = 2 * 1024 * 1024

    GEMINI_COMPATIBILITY_FALLBACK_STATUSES = {
        "SARVAM_TTS_NOT_CONFIGURED",
        "SARVAM_TTS_UNSUPPORTED_LANGUAGE",
        "SARVAM_TTS_OPUS_NOT_OGG",
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
                "VOICE TTS PATH: stage=sarvam_tts_stream_fast_fail "
                f"status={status} error_type={primary.get('error_type')} "
                "gemini_fallback=False",
                flush=True,
            )
            failed = dict(primary)
            failed["tts_path"] = "sarvam_http_stream_fast_fail"
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

        cache_key = f"sarvam-stream-opus:{language_code}:{spoken_text}"
        cached_audio = self._tts_cache.get(cache_key)
        if cached_audio:
            return self._success_result(
                cached_audio,
                spoken_text,
                language_code,
                cache_hit=True,
                first_byte_ms=0,
                stream_ms=0,
            )

        header_name = "api-" + "subscription-key"
        headers = {header_name: self.sarvam_api_key, "Content-Type": "application/json"}
        payload = {
            "text": spoken_text,
            "target_language_code": language_code,
            "speaker": self.TTS_SPEAKER,
            "model": self.TTS_MODEL,
            "pace": 1.1,
            "speech_sample_rate": self.TTS_SAMPLE_RATE,
            "output_audio_codec": self.TTS_OUTPUT_CODEC,
            "output_audio_bitrate": self.TTS_OUTPUT_BITRATE,
            "temperature": 0.4,
        }
        timeout = httpx.Timeout(
            connect=self.TTS_CONNECT_TIMEOUT_SECONDS,
            read=self.TTS_READ_TIMEOUT_SECONDS,
            write=3.0,
            pool=2.0,
        )

        started = time.perf_counter()
        first_byte_ms = None
        audio_parts: list[bytes] = []
        total_bytes = 0

        try:
            with self._sarvam_http_client.stream(
                "POST",
                self.TTS_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as response:
                if response.status_code != 200:
                    error_preview = response.read()[:300].decode("utf-8", errors="replace")
                    return {
                        "success": False,
                        "status": f"SARVAM_TTS_HTTP_{response.status_code}",
                        "error_type": "HTTPStatusError",
                        "error": error_preview,
                    }

                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    if first_byte_ms is None:
                        first_byte_ms = round((time.perf_counter() - started) * 1000)
                    total_bytes += len(chunk)
                    if total_bytes > self.TTS_MAX_AUDIO_BYTES:
                        return {
                            "success": False,
                            "status": "SARVAM_TTS_AUDIO_TOO_LARGE",
                            "error_type": "AudioSizeError",
                        }
                    audio_parts.append(chunk)

            audio_bytes = b"".join(audio_parts)
            if not audio_bytes:
                return {"success": False, "status": "SARVAM_TTS_EMPTY_AUDIO"}

            stream_ms = round((time.perf_counter() - started) * 1000)
            if not audio_bytes.startswith(b"OggS"):
                return {
                    "success": False,
                    "status": "SARVAM_TTS_OPUS_NOT_OGG",
                    "error_type": "AudioContainerError",
                    "first_byte_ms": first_byte_ms or stream_ms,
                    "stream_ms": stream_ms,
                }

            self._cache_tts(cache_key, audio_bytes)
            print(
                "VOICE TTS PATH: stage=sarvam_tts_http_stream_opus success=True "
                f"language={language_code} first_byte_ms={first_byte_ms or stream_ms} "
                f"stream_ms={stream_ms} audio_bytes={len(audio_bytes)} "
                "codec=opus bitrate=32k client_reused=True conversion_bypass=True",
                flush=True,
            )
            return self._success_result(
                audio_bytes,
                spoken_text,
                language_code,
                cache_hit=False,
                first_byte_ms=first_byte_ms or stream_ms,
                stream_ms=stream_ms,
            )
        except httpx.TimeoutException as error:
            return {
                "success": False,
                "status": "SARVAM_TTS_STREAM_TIMEOUT",
                "error_type": type(error).__name__,
                "first_byte_ms": first_byte_ms,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "SARVAM_TTS_STREAM_ERROR",
                "error_type": type(error).__name__,
                "error": str(error)[:300],
                "first_byte_ms": first_byte_ms,
            }

    def _success_result(
        self,
        audio_bytes: bytes,
        spoken_text: str,
        language_code: str,
        *,
        cache_hit: bool,
        first_byte_ms: int,
        stream_ms: int,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "status": "SYNTHESIZED_SARVAM_STREAM_CACHE" if cache_hit else "SYNTHESIZED_SARVAM_STREAM",
            "content": audio_bytes,
            "sample_rate": self.TTS_SAMPLE_RATE,
            "channels": 1,
            "sample_width": 2,
            "spoken_text": spoken_text,
            "model": self.TTS_MODEL,
            "voice": self.TTS_SPEAKER,
            "cache_hit": cache_hit,
            "tts_path": "sarvam_bulbul_v3_http_stream_opus",
            "language_code": language_code,
            "first_byte_ms": first_byte_ms,
            "stream_ms": stream_ms,
            "audio_codec": self.TTS_OUTPUT_CODEC,
            "mime_type": "audio/ogg",
            "file_name": "podx-reply.ogg",
            "encoded_audio": True,
        }

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
