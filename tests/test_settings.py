from app.core.settings import load_settings


def _clear_database_env(monkeypatch):
    monkeypatch.delenv("PODX_DATABASE_PATH", raising=False)
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)


def test_database_path_defaults_to_local_file(monkeypatch):
    _clear_database_env(monkeypatch)

    assert load_settings().database_path == "podx_v2.db"


def test_database_path_uses_railway_volume_when_attached(monkeypatch):
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")

    assert load_settings().database_path == "/data/podx_v2.db"


def test_relative_configured_database_path_moves_to_railway_volume(monkeypatch):
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PODX_DATABASE_PATH", "podx_v2.db")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")

    assert load_settings().database_path == "/data/podx_v2.db"


def test_absolute_configured_database_path_is_preserved(monkeypatch):
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PODX_DATABASE_PATH", "/custom/podx.db")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")

    assert load_settings().database_path == "/custom/podx.db"
