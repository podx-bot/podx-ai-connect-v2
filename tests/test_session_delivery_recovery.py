from app.database.database import Database
from app.models.session import ConversationStep
from app.repositories.delivery_log_repository import DeliveryLogRepository
from app.repositories.session_repository import SessionRepository


def test_stale_intermediate_session_recovers_to_main_menu(tmp_path):
    db = Database(str(tmp_path / "podx.db"))
    db.create_tables()
    db.execute(
        "INSERT INTO conversation_sessions(sender_mobile, step, data_json, updated_at) VALUES(?, ?, ?, datetime('now','-2 day'))",
        ("9000000001", ConversationStep.WORKER_LOCATION.value, '{"category":"cook"}'),
    )
    repo = SessionRepository(db)
    session = repo.get("9000000001")
    assert session.step == ConversationStep.MAIN_MENU
    assert session.data == {}
    db.close()


def test_recent_intermediate_session_is_preserved(tmp_path):
    db = Database(str(tmp_path / "podx.db"))
    db.create_tables()
    db.execute(
        "INSERT INTO conversation_sessions(sender_mobile, step, data_json, updated_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP)",
        ("9000000002", ConversationStep.WORKER_LOCATION.value, '{"category":"cook"}'),
    )
    repo = SessionRepository(db)
    session = repo.get("9000000002")
    assert session.step == ConversationStep.WORKER_LOCATION
    assert session.data["category"] == "cook"
    db.close()


def test_failed_recent_only_returns_latest_failed_message_state(tmp_path):
    db = Database(str(tmp_path / "podx.db"))
    db.create_tables()
    repo = DeliveryLogRepository(db)
    repo.save_status("m1", "9000000003", "failed", "temporary")
    repo.save_status("m1", "9000000003", "delivered", None)
    repo.save_status("m2", "9000000004", "failed", "blocked")
    failed = repo.failed_recent()
    assert [row["provider_message_id"] for row in failed] == ["m2"]
    assert repo.latest_for_message("m1")["status"] == "delivered"
    db.close()
