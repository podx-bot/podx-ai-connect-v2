from app.database.database import Database
from app.models.session import ConversationStep
from app.repositories.user_repository import UserRepository
from app.services.end_to_end_app_flow_service import EndToEndAppFlowService


class Session:
    def __init__(self):
        self.step = ConversationStep.WAITING_AREA
        self.data = {"language": "Telugu", "name": "Manohar", "entered_mobile": "9191"}


class Sessions:
    def __init__(self):
        self.session = Session()

    def get(self, sender):
        return self.session

    def save(self, sender):
        return None


class Base:
    def __init__(self, users, sessions):
        self.user_repository = users
        self.session_registry = sessions


class Inner:
    def __init__(self, base):
        self.base_conversation = base
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "DOWNSTREAM"


def build(tmp_path):
    database = Database(str(tmp_path / "handoff.db"))
    database.create_tables()
    users = UserRepository(database)
    sessions = Sessions()
    base = Base(users, sessions)
    inner = Inner(base)
    return database, users, sessions, inner, EndToEndAppFlowService(inner, base_conversation=base)


def test_profile_completion_offers_optional_face_welcome(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        reply = flow.process("9191", "Vuyyuru")
        assert "PODX ప్రొఫైల్ సిద్ధమైంది" in reply
        assert "Face Welcome" in reply
        assert "consent" in reply
        assert sessions.session.data["face_welcome_handoff_pending"] is True
        assert users.find_by_whatsapp_mobile("9191")["registration_complete"] == 1
        assert inner.calls == []
    finally:
        database.close()


def test_yes_moves_to_photo_prompt_and_consent(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        flow.process("9191", "Vuyyuru")
        reply = flow.process("9191", "అవును")
        assert "clear front-face photo" in reply
        assert sessions.session.data["face_welcome_handoff_pending"] is False
        assert sessions.session.data["face_welcome_photo_pending"] is True
        state = flow.face_welcome.repository.get("9191")
        assert state["consent_status"] == "ACCEPTED"
        assert inner.calls == []
    finally:
        database.close()


def test_skip_goes_to_universal_open_ask_without_blocking_profile(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        flow.process("9191", "Vuyyuru")
        reply = flow.process("9191", "ఇప్పుడు వద్దు")
        assert "Face Welcome" in reply
        assert "మీకు ఏం కావాలో మీ మాటల్లో చెప్పండి" in reply
        assert sessions.session.data["face_welcome_handoff_pending"] is False
        assert sessions.session.data["face_welcome_photo_pending"] is False
        state = flow.face_welcome.repository.get("9191")
        assert state["consent_status"] == "DECLINED"
        assert inner.calls == []
    finally:
        database.close()
