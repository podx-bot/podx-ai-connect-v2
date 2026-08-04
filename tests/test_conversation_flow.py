from pathlib import Path

from app.database.database import Database
from app.repositories.user_repository import UserRepository
from app.services.conversation_service import ConversationService
from app.services.session_registry import SessionRegistry


def build_service(tmp_path: Path):
    database = Database(str(tmp_path / "test.db"))
    database.create_tables()

    service = ConversationService(
        user_repository=UserRepository(database),
        session_registry=SessionRegistry()
    )
    return service, database


def test_registration_and_menu(tmp_path):
    service, database = build_service(tmp_path)

    sender = "919999999999"

    assert "మొబైల్" in service.process(sender, "Hi")
    assert "పేరు" in service.process(sender, "9999999999")
    assert "భాష" in service.process(sender, "Manohar")
    assert "ప్రాంతం" in service.process(sender, "1")
    assert "Registration" in service.process(sender, "Vuyyuru")
    assert "Job Seeker" in service.process(sender, "1")

    database.close()
