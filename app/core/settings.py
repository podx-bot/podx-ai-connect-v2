import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_path: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_api_version: str
    whatsapp_webhook_verify_token: str
    sarvam_api_key: str
    sarvam_stt_model: str
    sarvam_stt_timeout_seconds: int
    gemini_api_key: str
    gemini_voice_model: str
    gemini_voice_max_bytes: int
    gemini_tts_model: str
    gemini_tts_voice: str
    openai_api_key: str
    openai_vision_model: str
    image_ai_min_confidence: float
    voice_reply_enabled: bool
    voice_reply_max_chars: int


def _database_path() -> str:
    """Resolve a database path that persists on Railway when a Volume is attached."""
    configured = os.getenv("PODX_DATABASE_PATH", "").strip()
    volume_mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()

    if volume_mount:
        configured_path = Path(configured) if configured else Path("podx_v2.db")
        if not configured_path.is_absolute():
            return str(Path(volume_mount) / configured_path.name)

    return configured or "podx_v2.db"


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, min(value, 1.0))


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def load_settings() -> Settings:
    return Settings(
        database_path=_database_path(),
        whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
        whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v23.0").strip(),
        whatsapp_webhook_verify_token=os.getenv(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
            "podx_verify_2026",
        ).strip(),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", "").strip(),
        sarvam_stt_model=os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip(),
        sarvam_stt_timeout_seconds=_positive_int_env("SARVAM_STT_TIMEOUT_SECONDS", 8),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_voice_model=os.getenv(
            "GEMINI_VOICE_MODEL",
            "gemini-3.6-flash",
        ).strip(),
        gemini_voice_max_bytes=_positive_int_env(
            "GEMINI_VOICE_MAX_BYTES",
            18 * 1024 * 1024,
        ),
        gemini_tts_model=os.getenv(
            "GEMINI_TTS_MODEL",
            "gemini-3.1-flash-tts-preview",
        ).strip(),
        gemini_tts_voice=os.getenv(
            "GEMINI_TTS_VOICE",
            "Sulafat",
        ).strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", "gpt-5").strip(),
        image_ai_min_confidence=_float_env("PODX_IMAGE_AI_MIN_CONFIDENCE", 0.65),
        voice_reply_enabled=_bool_env("PODX_VOICE_REPLY_ENABLED", True),
        voice_reply_max_chars=_positive_int_env(
            "PODX_VOICE_REPLY_MAX_CHARS",
            900,
        ),
    )
