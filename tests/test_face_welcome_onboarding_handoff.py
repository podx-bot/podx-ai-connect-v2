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


def complete_profile(flow):
    return flow.process("9191", "Vuyyuru")


def test_profile_completion_goes_directly_to_open_ask(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        reply = complete_profile(flow)
        assert "PODX ప్రొఫైల్ సిద్ధమైంది" in reply
        assert "ఇప్పుడు మీకు ఏం కావాలో చెప్పండి" in reply
        assert "Face Welcome" not in reply
        assert "face_welcome_handoff_pending" not in sessions.session.data
        assert "face_welcome_shop_handoff_pending" not in sessions.session.data
        assert users.find_by_whatsapp_mobile("9191")["registration_complete"] == 1
        assert inner.calls == []
    finally:
        database.close()


def test_no_face_welcome_outside_eligible_shop_context(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        complete_profile(flow)
        assert flow.offer_face_welcome_for_shop("9191", eligible=False, business_name="Demo Shop") is None
        assert "face_welcome_shop_handoff_pending" not in sessions.session.data
        assert flow.face_welcome.repository.get("9191") is None
    finally:
        database.close()


def test_first_eligible_shop_interaction_offers_contextual_opt_in(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        complete_profile(flow)
        reply = flow.offer_face_welcome_for_shop("9191", eligible=True, business_name="Demo Shop")
        assert "Demo Shop" in reply
        assert "Face Welcome" in reply
        assert "Enable / Not now" in reply
        assert "normal profile photo" in reply
        assert sessions.session.data["face_welcome_shop_handoff_pending"] is True
        assert flow.face_welcome.repository.get("9191") is None
    finally:
        database.close()


def test_enable_records_consent_and_requests_separate_face_photo(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        complete_profile(flow)
        flow.offer_face_welcome_for_shop("9191", eligible=True, business_name="Demo Shop")
        reply = flow.process("9191", "Enable")
        assert "clear front-face photo" in reply
        assert sessions.session.data["face_welcome_shop_handoff_pending"] is False
        assert sessions.session.data["face_welcome_photo_pending"] is True
        state = flow.face_welcome.repository.get("9191")
        assert state["consent_status"] == "ACCEPTED"
        assert not state.get("photo_sha256")
        assert inner.calls == []
    finally:
        database.close()


def test_skip_continues_normal_flow_and_suppresses_repeat_offer(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        complete_profile(flow)
        flow.offer_face_welcome_for_shop("9191", eligible=True, business_name="Demo Shop")
        reply = flow.process("9191", "Not now")
        assert "normal shop/PODX flow" in reply
        assert sessions.session.data["face_welcome_shop_handoff_pending"] is False
        assert sessions.session.data["face_welcome_photo_pending"] is False
        state = flow.face_welcome.repository.get("9191")
        assert state["consent_status"] == "DECLINED"
        assert flow.offer_face_welcome_for_shop("9191", eligible=True, business_name="Demo Shop") is None
        assert inner.calls == []
    finally:
        database.close()


def test_disable_deletes_saved_face_enrollment_and_allows_no_silent_reuse(tmp_path):
    database, users, sessions, inner, flow = build(tmp_path)
    try:
        complete_profile(flow)
        flow.offer_face_welcome_for_shop("9191", eligible=True, business_name="Demo Shop")
        flow.process("9191", "అవును")
        saved = flow.face_welcome.accept_photo("9191", b"new-explicit-face-enrollment-photo")
        assert "enrollment save" in saved
        state = flow.face_welcome.repository.get("9191")
        assert state["photo_sha256"]

        reply = flow.face_welcome.process_text("9191", "disable face welcome")
        assert "Face Welcome off" in reply
        state = flow.face_welcome.repository.get("9191")
        assert not state or not state.get("photo_sha256")
    finally:
        database.close()
