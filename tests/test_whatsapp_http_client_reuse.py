from pathlib import Path


def test_whatsapp_service_reuses_one_http_client_for_transport_calls():
    source = Path("app/whatsapp/whatsapp_service.py").read_text(encoding="utf-8")

    assert "self._http_client = httpx.Client(" in source
    assert "response = self._http_client.post(" in source
    assert "metadata_response = self._http_client.get(" in source
    assert "media_response = self._http_client.get(" in source
    assert "response = httpx.post(" not in source
    assert "metadata_response = httpx.get(" not in source
    assert "media_response = httpx.get(" not in source


def test_whatsapp_media_download_reports_substage_timings():
    source = Path("app/whatsapp/whatsapp_service.py").read_text(encoding="utf-8")

    assert '"metadata_ms"' in source
    assert '"download_ms"' in source
    assert '"media_total_ms"' in source
