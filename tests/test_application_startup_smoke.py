def test_application_starts_with_universal_image_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("PODX_DATABASE_PATH", str(tmp_path / "startup.db"))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "test-whatsapp-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key")

    from app.api.app_factory import create_app

    app = create_app()
    try:
        container = app.state.container
        assert container.universal_live_capture_service is not None
        assert container.universal_image_service is not None
        assert container.universal_image_pending_repository is not None
        assert container.conversation_os_runtime_service is not None
        assert container.conversation_turn_ledger_repository is not None
        assert container.customer_facing_response_policy is not None
        assert container.conversation_service is container.customer_facing_response_policy
        assert container.customer_facing_response_policy.delegate is container.conversation_os_runtime_service
    finally:
        app.state.container.close()
