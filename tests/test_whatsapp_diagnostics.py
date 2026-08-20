from fastapi.testclient import TestClient


def test_whatsapp_diagnostics_exposes_only_non_secret_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("PODX_DATABASE_PATH", str(tmp_path / "diagnostics.db"))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "super-secret-token")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key")

    from app.api.app_factory import create_app

    app = create_app()
    try:
        client = TestClient(app)
        response = client.get("/debug/whatsapp-diagnostics")
        assert response.status_code == 200
        payload = response.json()
        assert "checks" in payload
        assert "checkpoints" in payload
        assert "inbound_messages" in payload["checkpoints"]
        assert "conversation_turns" in payload["checkpoints"]
        rendered = response.text
        assert "super-secret-token" not in rendered
        assert "sender_mobile" not in rendered
        assert "message_text" not in rendered
    finally:
        app.state.container.close()
