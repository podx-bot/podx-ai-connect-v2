from pathlib import Path

from app.database.database import Database
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
        session_registry=SessionRegistry(session_repository)
    )
    return service, database


def register_user(service, sender: str):
    assert "మొబైల్" in service.process(sender, "Hi")
    assert "పేరు" in service.process(sender, "9999999999")
    assert "భాష" in service.process(sender, "Manohar")
    assert "ప్రాంతం" in service.process(sender, "1")
    assert "Buyer" in service.process(sender, "Vuyyuru")
    assert "Registration" in service.process(sender, "5")


def test_registration_and_worker_menu(tmp_path):
    service, database = build_service(tmp_path / "test.db")
    sender = "919999999999"

    register_user(service, sender)
    assert "పని" in service.process(sender, "1")

    database.close()


def test_registration_accepts_multiple_roles(tmp_path):
    service, database = build_service(tmp_path / "multi-role-registration.db")
    sender = "919111111111"

    service.process(sender, "Hi")
    service.process(sender, "9111111111")
    service.process(sender, "Multi Role User")
    service.process(sender, "1")
    response = service.process(sender, "Vijayawada")
    assert "ఒకటి లేదా ఎక్కువ" in response

    response = service.process(sender, "1,2,4,5")
    assert "Registration" in response
    capabilities = service.user_repository.list_capabilities(sender)
    assert capabilities == ["BUYER", "SELLER", "SERVICE_PROVIDER", "WORKER"]

    database.close()


def test_registration_all_option_seeds_all_capabilities(tmp_path):
    service, database = build_service(tmp_path / "all-roles.db")
    sender = "919222222222"

    service.process(sender, "Hi")
    service.process(sender, "9222222222")
    service.process(sender, "All Roles User")
    service.process(sender, "1")
    service.process(sender, "Vuyyuru")
    service.process(sender, "7")

    assert set(service.user_repository.list_capabilities(sender)) == {
        "BUYER",
        "SELLER",
        "SERVICE_CUSTOMER",
        "SERVICE_PROVIDER",
        "WORKER",
        "EMPLOYER",
    }
    database.close()


def test_session_survives_service_restart(tmp_path):
    database_path = tmp_path / "restart.db"
    sender = "918888888888"

    service, database = build_service(database_path)
    assert "మొబైల్" in service.process(sender, "Hi")
    assert "పేరు" in service.process(sender, "8888888888")
    database.close()

    restarted_service, restarted_database = build_service(database_path)
    response = restarted_service.process(sender, "Restart Test User")

    assert "భాష" in response
    restarted_database.close()


def test_menu_recovery_for_registered_user(tmp_path):
    service, database = build_service(tmp_path / "menu.db")
    sender = "917777777777"

    register_user(service, sender)
    service.process(sender, "1")
    assert "Experience" in service.process(sender, "2")

    response = service.process(sender, "Menu")
    assert "ఉద్యోగం కావాలి" in response
    assert "వర్కర్స్ కావాలి" in response

    database.close()


def test_back_moves_to_previous_step(tmp_path):
    service, database = build_service(tmp_path / "back.db")
    sender = "916666666666"

    register_user(service, sender)
    service.process(sender, "1")
    service.process(sender, "2")

    response = service.process(sender, "Back")
    assert "పని కోసం" in response

    database.close()


def test_restart_resets_conversation(tmp_path):
    service, database = build_service(tmp_path / "reset.db")
    sender = "915555555555"

    service.process(sender, "Hi")
    service.process(sender, "9555555555")
    assert "reset" in service.process(sender, "Restart").lower()
    assert "మొబైల్" in service.process(sender, "Hi")

    database.close()
