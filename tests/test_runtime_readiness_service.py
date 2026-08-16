from types import SimpleNamespace

from app.services.runtime_readiness_service import RuntimeReadinessService


def _settings(**overrides):
    base = dict(
        whatsapp_access_token="",
        whatsapp_phone_number_id="",
        whatsapp_webhook_verify_token="token",
        sarvam_api_key="",
        gemini_api_key="",
        openai_api_key="",
        voice_reply_enabled=True,
        google_maps_api_key="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_missing_optional_providers_degrade_without_exception():
    result = RuntimeReadinessService(_settings()).check()
    assert result.whatsapp_ready is False
    assert result.webhook_ready is True
    assert result.voice_stt_ready is False
    assert result.voice_tts_ready is False
    assert result.image_ai_ready is False
    assert result.maps_ready is False
    assert result.warnings


def test_configured_providers_report_ready():
    result = RuntimeReadinessService(
        _settings(
            whatsapp_access_token="wa",
            whatsapp_phone_number_id="phone",
            sarvam_api_key="sarvam",
            gemini_api_key="gemini",
            openai_api_key="openai",
            google_maps_api_key="maps",
        )
    ).check()
    assert result.whatsapp_ready is True
    assert result.voice_stt_ready is True
    assert result.voice_tts_ready is True
    assert result.image_ai_ready is True
    assert result.maps_ready is True
