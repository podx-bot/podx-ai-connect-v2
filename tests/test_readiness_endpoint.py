from types import SimpleNamespace

from app.api.routes.health import _readiness_payload


def _settings(**overrides):
    values = dict(
        whatsapp_access_token="wa",
        whatsapp_phone_number_id="phone",
        whatsapp_webhook_verify_token="verify",
        sarvam_api_key="sarvam",
        gemini_api_key="gemini",
        openai_api_key="openai",
        voice_reply_enabled=True,
        google_maps_api_key="maps",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_readiness_is_ready_when_critical_dependencies_are_available():
    result = _readiness_payload(_settings(), database_ok=True)
    assert result["status"] == "ready"
    assert result["live_test_ready"] is True
    assert result["critical"] == {"whatsapp_send": True, "webhook_verify": True}
    assert result["payment_policy"]["podx_platform_charge"] == 0
    assert result["payment_policy"]["gateway_required_for_testing"] is False


def test_optional_provider_gap_does_not_block_text_live_testing():
    result = _readiness_payload(
        _settings(
            sarvam_api_key="",
            gemini_api_key="",
            openai_api_key="",
            google_maps_api_key="",
            voice_reply_enabled=False,
        ),
        database_ok=True,
    )
    assert result["status"] == "ready"
    assert result["live_test_ready"] is True
    assert result["optional"]["voice_stt"] is False
    assert result["optional"]["image_ai"] is False
    assert result["optional"]["maps"] is False
    assert result["warnings"]


def test_database_or_whatsapp_gap_blocks_live_test_ready_flag():
    result = _readiness_payload(
        _settings(whatsapp_access_token="", whatsapp_phone_number_id=""),
        database_ok=False,
    )
    assert result["status"] == "degraded"
    assert result["live_test_ready"] is False
    assert result["database_ready"] is False
    assert result["critical"]["whatsapp_send"] is False
