from app.repositories.conversation_turn_ledger_repository import ConversationTurnLedgerRepository
from app.services.conversation_os_runtime_service import ConversationOSRuntimeService


class FakeDelegate:
    def __init__(self):
        self.messages = []

    def process(self, sender_mobile: str, message: str) -> str:
        self.messages.append((sender_mobile, message))
        return "✅ understood"


def build_service(tmp_path):
    delegate = FakeDelegate()
    ledger = ConversationTurnLedgerRepository(str(tmp_path / "conversation-os.db"))
    service = ConversationOSRuntimeService(
        delegate=delegate,
        ledger_repository=ledger,
        request_extractor=None,
    )
    return service, delegate, ledger


def test_first_turn_is_not_delayed_or_rewritten(tmp_path):
    service, delegate, ledger = build_service(tmp_path)
    original = "నాకు 10 కేజీల చికెన్ కావాలి"

    reply = service.process("buyer-1", original)

    assert reply == "✅ understood"
    assert delegate.messages == [("buyer-1", original)]
    state = ledger.load_state("buyer-1")
    assert state["active_entity"] == "current request"
    assert state["known_fields"]["request_text"] == original


def test_short_variant_followup_keeps_original_request_context(tmp_path):
    service, delegate, ledger = build_service(tmp_path)
    service.process("buyer-1", "నాకు 10 కేజీల చికెన్ కావాలి")

    service.process("buyer-1", "బోన్లెస్ కావాలి")
    routed = delegate.messages[-1][1]
    state = ledger.load_state("buyer-1")

    assert "Original user request: నాకు 10 కేజీల చికెన్ కావాలి" in routed
    assert "User's new message: బోన్లెస్ కావాలి" in routed
    assert "బోన్లెస్ కావాలి" in state["known_fields"]["constraints"]
    assert ledger.recent_turns("buyer-1")[0]["turn_kind"] == "UPDATE_EXISTING"


def test_contextual_question_keeps_previous_user_and_bot_turn(tmp_path):
    service, delegate, ledger = build_service(tmp_path)
    service.process("buyer-1", "10 kg chicken కావాలి")
    service.process("buyer-1", "బోన్లెస్ కావాలి")

    service.process("buyer-1", "రేట్ ఎంత?")
    routed = delegate.messages[-1][1]

    assert "Original user request: 10 kg chicken కావాలి" in routed
    assert "Previous PODX reply context: ✅ understood" in routed
    assert "User's new message: రేట్ ఎంత?" in routed
    assert ledger.recent_turns("buyer-1")[0]["turn_kind"] == "QUESTION"


class BrokenLedger:
    def load_state(self, user_id):
        raise RuntimeError("db unavailable")


def test_runtime_fails_open_to_existing_delegate():
    delegate = FakeDelegate()
    service = ConversationOSRuntimeService(delegate=delegate, ledger_repository=BrokenLedger())
    reply = service.process("buyer-1", "hello")
    assert reply == "✅ understood"
    assert delegate.messages[-1] == ("buyer-1", "hello")
