import pytest

from app.database.database import Database
from app.repositories.capability_repository import CapabilityRepository


def build_repo(tmp_path):
    database = Database(str(tmp_path / "capabilities.db"))
    database.create_tables()
    return database, CapabilityRepository(database)


def test_user_can_hold_multiple_capabilities(tmp_path):
    database, repository = build_repo(tmp_path)
    try:
        repository.add_many(
            "9199",
            ["BUYER", "SELLER", "SERVICE_PROVIDER"],
            source="registration",
        )

        assert repository.list_for_user("9199") == [
            "BUYER",
            "SELLER",
            "SERVICE_PROVIDER",
        ]
        assert repository.has("9199", "SELLER") is True
        assert repository.has("9199", "WORKER") is False
    finally:
        database.close()


def test_capability_add_is_idempotent_and_source_can_update(tmp_path):
    database, repository = build_repo(tmp_path)
    try:
        repository.add("9199", "WORKER", source="registration")
        repository.add("9199", "worker", source="conversation")

        assert repository.list_for_user("9199") == ["WORKER"]
        row = database.fetchone(
            "SELECT source FROM user_capabilities WHERE whatsapp_mobile = ? AND capability = ?",
            ("9199", "WORKER"),
        )
        assert row["source"] == "conversation"
    finally:
        database.close()


def test_invalid_capability_is_rejected(tmp_path):
    database, repository = build_repo(tmp_path)
    try:
        with pytest.raises(ValueError):
            repository.add("9199", "UNKNOWN_ROLE")
    finally:
        database.close()
