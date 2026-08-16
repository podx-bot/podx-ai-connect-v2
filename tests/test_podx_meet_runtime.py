from app.repositories.podx_meet_repository import PodxMeetRepository
from app.services.podx_meet_aware_conversation_service import PodxMeetAwareConversationService
from app.services.podx_meet_runtime_service import PodxMeetRuntimeService


class FakeUsers:
    def __init__(self):
        self.rows = {
            "host": {"registration_complete": 1, "area": "Vijayawada"},
            "buyer": {"registration_complete": 1, "area": "Vijayawada"},
            "other": {"registration_complete": 1, "area": "Guntur"},
        }

    def find_by_whatsapp_mobile(self, user_id):
        return self.rows.get(str(user_id))


class Delegate:
    def __init__(self):
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return f"BASE:{message}"


def build(tmp_path):
    repo = PodxMeetRepository(str(tmp_path / "meet.db"))
    runtime = PodxMeetRuntimeService(repo, FakeUsers())
    return repo, runtime


def test_meet_create_find_join_leave_and_cancel(tmp_path):
    repo, runtime = build(tmp_path)

    created = runtime.process("host", "MEET CREATE Local Products Demo | Sunday 5 PM | Vijayawada | Bring samples")
    assert "#1" in created

    found = runtime.process("buyer", "MEET FIND")
    assert "Local Products Demo" in found
    assert "Vijayawada" in found

    joined = runtime.process("buyer", "MEET JOIN 1")
    assert "joined" in joined.lower()
    assert repo.attendee_count(1) == 1

    duplicate = runtime.process("buyer", "MEET JOIN 1")
    assert "ఇప్పటికే" in duplicate or "already" in duplicate.lower()
    assert repo.attendee_count(1) == 1

    denied = runtime.process("buyer", "MEET CANCEL 1")
    assert "host" in denied.lower()

    left = runtime.process("buyer", "MEET LEAVE 1")
    assert "leave" in left.lower()
    assert repo.attendee_count(1) == 0

    cancelled = runtime.process("host", "MEET CANCEL 1")
    assert "cancelled" in cancelled.lower()
    assert repo.get(1)["status"] == "CANCELLED"


def test_find_falls_back_to_open_meets_when_saved_area_has_none(tmp_path):
    repo, runtime = build(tmp_path)
    repo.create("host", "Guntur Seller Meet", "Tomorrow 6 PM", "Guntur", "")

    reply = runtime.process("buyer", "MEET FIND")

    assert "Guntur Seller Meet" in reply


def test_wrapper_only_intercepts_meet_messages(tmp_path):
    _, runtime = build(tmp_path)
    delegate = Delegate()
    wrapper = PodxMeetAwareConversationService(runtime, delegate)

    base_reply = wrapper.process("buyer", "I need rice")
    assert base_reply == "BASE:I need rice"
    assert delegate.calls == [("buyer", "I need rice")]

    meet_reply = wrapper.process("buyer", "MEET HELP")
    assert "MEET CREATE" in meet_reply
    assert delegate.calls == [("buyer", "I need rice")]
