from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeReadiness:
    whatsapp_ready: bool
    webhook_ready: bool
    voice_stt_ready: bool
    voice_tts_ready: bool
    image_ai_ready: bool
    maps_ready: bool
    warnings: tuple[str, ...]


class RuntimeReadinessService:
    """Non-fatal production configuration readiness checks.

    Missing optional providers should degrade features instead of crashing startup.
    Critical WhatsApp fields are surfaced as readiness warnings so admin/health
    tooling can report them before live testing.
    """

    def __init__(self, settings) -> None:
        self.settings = settings

    def check(self) -> RuntimeReadiness:
        warnings: list[str] = []
        whatsapp_ready = bool(
            str(getattr(self.settings, "whatsapp_access_token", "") or "").strip()
            and str(getattr(self.settings, "whatsapp_phone_number_id", "") or "").strip()
        )
        webhook_ready = bool(str(getattr(self.settings, "whatsapp_webhook_verify_token", "") or "").strip())
        if not whatsapp_ready:
            warnings.append("WhatsApp send credentials are incomplete")
        if not webhook_ready:
            warnings.append("WhatsApp webhook verify token is missing")

        sarvam = bool(str(getattr(self.settings, "sarvam_api_key", "") or "").strip())
        gemini = bool(str(getattr(self.settings, "gemini_api_key", "") or "").strip())
        openai = bool(str(getattr(self.settings, "openai_api_key", "") or "").strip())
        voice_stt_ready = sarvam or gemini
        voice_tts_ready = gemini and bool(getattr(self.settings, "voice_reply_enabled", False))
        image_ai_ready = openai or gemini
        maps_ready = bool(str(getattr(self.settings, "google_maps_api_key", "") or "").strip())

        if not voice_stt_ready:
            warnings.append("Voice transcription providers are not configured")
        if getattr(self.settings, "voice_reply_enabled", False) and not voice_tts_ready:
            warnings.append("Voice replies are enabled but Gemini TTS is unavailable")
        if not image_ai_ready:
            warnings.append("Image AI providers are not configured")
        if not maps_ready:
            warnings.append("Google Maps key is not configured; route fallback will be used")

        return RuntimeReadiness(
            whatsapp_ready=whatsapp_ready,
            webhook_ready=webhook_ready,
            voice_stt_ready=voice_stt_ready,
            voice_tts_ready=voice_tts_ready,
            image_ai_ready=image_ai_ready,
            maps_ready=maps_ready,
            warnings=tuple(warnings),
        )
