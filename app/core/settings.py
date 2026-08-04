import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_path: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_api_version: str
    whatsapp_webhook_verify_token: str


def load_settings() -> Settings:
    return Settings(
        database_path=os.getenv(
            "PODX_DATABASE_PATH",
            "podx_v2.db"
        ).strip(),
        whatsapp_access_token=os.getenv(
            "WHATSAPP_ACCESS_TOKEN",
            ""
        ).strip(),
        whatsapp_phone_number_id=os.getenv(
            "WHATSAPP_PHONE_NUMBER_ID",
            ""
        ).strip(),
        whatsapp_api_version=os.getenv(
            "WHATSAPP_API_VERSION",
            "v23.0"
        ).strip(),
        whatsapp_webhook_verify_token=os.getenv(
            "WHATSAPP_WEBHOOK_VERIFY_TOKEN",
            "podx_verify_2026"
        ).strip()
    )
