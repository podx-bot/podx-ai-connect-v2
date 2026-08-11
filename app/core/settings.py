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
    gemini_api_key: str
    gemini_voice_model: str
    gemini_voice_max_bytes: int


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


def load_settings() -> Settings:
    return Settings(
        database_path=_database_path(),
        whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
        whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
        whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v23.0").strip(),
        whatsapp_webhook_verify_token=os.getenv(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
            "podx_verify_2026"
        ).strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_voice_model=os.getenv(
            "GEMINI_VOICE_MODEL",
            "gemini-2.5-flash"
        ).strip(),
        gemini_voice_max_bytes=_positive_int_env(
            "GEMINI_VOICE_MAX_BYTES",
            18 * 1024 * 1024
        )
    )
