from app.core.container import AppContainer


def test_container_wires_demand_intelligence_into_live_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "podx.db"))
    container = AppContainer()
    try:
        assert container.demand_intelligence_service is not None
        assert container.universal_live_capture_service.demand_intelligence is container.demand_intelligence_service
        assert container.demand_signal_repository.count() == 0
    finally:
        container.close()
