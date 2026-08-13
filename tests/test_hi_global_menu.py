from pathlib import Path

from app.database.database import Database
from app.models.session import ConversationStep
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.conversation_service import ConversationService
from app.services.session_registry import SessionRegistry


def build_service(database_path: Path):
    database = Database(str(database_path))
    database.create_tables()
    session_repository = SessionRepository(database)
    service = ConversationService(
        user_repository=UserRepository(database),
        session_registry=SessionRegistry(session_repository),
    )
    return service, database


def register_user(service, sender: str):
    service.process(sender, "Hi")
    service.process(sender, "9999999999")
    service.process(sender, "Manohar")
    service.process(sender, "1")
    service.process(sender, "Vuyyuru")
    service.process(sender, "6")


def test_hi_returns_registered_user_to_main_menu_from_employer_location(tmp_path):
    service, database = build_service(tmp_path / "hi-global.db")
    sender = "919999999999"

    register_user(service, sender)
    service.process(sender, "2")
    service.process(sender, "2")
    service.process(sender, "10 workers wanted")

    session = service.session_registry.get(sender)
    assert session.step == ConversationStep.EMPLOYER_LOCATION

    response = service.process(sender, "Hi")

    assert "ఉద్యోగం కావాలి" in response
    assert "వర్కర్స్ కావాలి" in response
    assert session.step == ConversationStep.MAIN_MENU
    assert session.data == {}

    database.close()
