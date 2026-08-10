import pytest

from app.database.database import Database
from app.repositories.user_repository import UserRepository
from app.repositories.session_repository import SessionRepository
from app.services.session_registry import SessionRegistry
from app.services.conversation_service import ConversationService
from app.models.session import ConversationStep


@pytest.fixture
def setup_services(tmp_path):
    db_path = str(tmp_path / "test_db.sqlite")
    db = Database(db_path)
    db.create_tables()
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)
    session_registry = SessionRegistry(session_repo)
    conv_service = ConversationService(user_repo, session_registry)
    return db, user_repo, session_repo, conv_service


def test_employer_multi_message_sequence_persists_between_requests(setup_services):
    db, user_repo, session_repo, conv_service = setup_services
    sender = "919999999999"

    # Ensure user is registered so MAIN_MENU is available
    user_repo.create_or_update_registration(whatsapp_mobile=sender, entered_mobile="9999999999", name="Test", language="English", area="Hyderabad")

    # First webhook: user selects option 2 (Employer)
    reply1 = conv_service.process(sender, "2")
    assert "Employer workflow" in reply1 or "Employer workflow ప్రారంభమవుతుంది" in reply1
    assert "👷" in reply1

    # Simulate separate webhook/process by creating a new SessionRegistry to force repository load
    fresh_registry = SessionRegistry(session_repo)
    session = fresh_registry.get(sender)
    assert session.step == ConversationStep.EMPLOYER_SERVICE

    # Second webhook: user picks a service (2 -> Catering for example)
    reply2 = conv_service.process(sender, "2")
    assert "మీ job requirement" in reply2 or "job requirement" in reply2

    fresh_registry2 = SessionRegistry(session_repo)
    session2 = fresh_registry2.get(sender)
    assert session2.step == ConversationStep.EMPLOYER_REQUIREMENT

    # Third webhook: user sends requirement details
    reply3 = conv_service.process(sender, "Need 3 cooks for lunchtime")
    assert "WhatsApp Attachment" in reply3 or "Location" in reply3

    fresh_registry3 = SessionRegistry(session_repo)
    session3 = fresh_registry3.get(sender)
    assert session3.step == ConversationStep.EMPLOYER_LOCATION
