from app.repositories.conversation_turn_ledger_repository import ConversationTurnLedgerRepository
from app.services.conversation_os_runtime_service import ConversationOSRuntimeService


class FakeDelegate:
    def __init__(self):
        self.messages = []

    def process(self, sender_mobile: str, message: str) -> str:
        self.messages.append((sender_mobile, message))
        return "✅ understood"


class FakeExtractor:
    def extract(self, message: str) -> dict:
        lowered = message.casefold()
        if "electrician" in lowered:
            return {
                "success": True,
                "request": {
                    "side": "NEED",
                    "domain": "SERVICE",
                    "subject": "electrician",
                    "quantity": None,
                    "unit": None,
                    "price": None,
                    "currency": None,
                    "when_text": None,
                    "location_text": None,
                    "constraints": [],
                    "confidence": 0.98,
                },
            }
        return {
            "success": True,
            "request": {
                "side": "NEED",
                "domain": "PRODUCT",
                "subject": "chicken",
                "quantity": 10,
                "unit": "kg",
                "price": None,
                "currency": None,
                "when_text": None,
                "location_text": None,
                "constraints": [],
                "confidence": 0.97,
            },
        }


def build_service(tmp_path):
    delegate = FakeDelegate()
    ledger = ConversationTurnLedgerRepository(str(tmp_path / "conversation-os.db"))
    service = ConversationOSRuntimeService(
        delegate=delegate,
        ledger_repository=ledger,
        request_extractor=FakeExtractor(),
    )
    return service, delegate, ledger


def test_runtime_preserves_active_request_for_short_variant_followup(tmp_path):
    service, delegate, ledger = build_service(tmp_path)

    service.process("buyer-1", "నాకు 10 కేజీల చికెన్ కావాలి")
    first = ledger.load_state("buyer-1")
    assert first["active_entity"] == "chicken"
    assert first["known_fields"]["quantity"] == 10
    assert first["known_fields"]["unit"] == "kg"

    service.process("buyer-1", "బోన్లెస్ కావాలి")
    second = ledger.load_state("buyer-1")
    routed = delegate.messages[-1][1]

    assert second["active_entity"] == "chicken"
    assert second["known_fields"]["quantity"] == 10
    assert "బోన్లెస్ కావాలి" in second["known_fields"]["constraints"]
    assert "chicken" in routed
    assert "quantity=10" in routed
    assert "బోన్లెస్ కావాలి" in routed
    assert ledger.recent_turns("buyer-1")[0]["turn_kind"] == "UPDATE_EXISTING"


def test_runtime_switches_context_for_explicit_new_subject(tmp_path):
    service, delegate, ledger = build_service(tmp_path)

    service.process("buyer-1", "నాకు 10 కేజీల చికెన్ కావాలి")
    service.process("buyer-1", "నాకు electrician కూడా కావాలి")

    state = ledger.load_state("buyer-1")
    assert state["active_entity"] == "electrician"
    assert state["active_flow"] == "SERVICE_NEED"
    assert ledger.recent_turns("buyer-1")[0]["turn_kind"] == "NEW_TOPIC"
    assert delegate.messages[-1][1] == "నాకు electrician కూడా కావాలి"


def test_runtime_uses_previous_bot_reply_for_contextual_question(tmp_path):
    service, delegate, ledger = build_service(tmp_path)
    service.process("buyer-1", "నాకు 10 కేజీల చికెన్ కావాలి")

    service.process("buyer-1", "రేట్ ఎంత?")
    routed = delegate.messages[-1][1]

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
