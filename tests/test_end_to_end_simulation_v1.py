from app.services.end_to_end_app_flow_service import EndToEndAppFlowService
from app.services.natural_conversation_orchestrator import NaturalConversationOrchestrator
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


class Users:
    def __init__(self, registered=True):
        self.registered = registered

    def find_by_whatsapp_mobile(self, sender):
        if not self.registered:
            return None
        return {"whatsapp_mobile": sender, "registration_complete": 1, "name": "Test User"}


class Step:
    def __init__(self, name):
        self.name = name


class Session:
    def __init__(self, name):
        self.step = Step(name)
        self.data = {}


class Sessions:
    def __init__(self, step="MAIN_MENU"):
        self.step = step

    def get(self, sender):
        return Session(self.step)


class BaseConversation:
    def __init__(self, registered=True, step="MAIN_MENU"):
        self.user_repository = Users(registered)
        self.session_registry = Sessions(step)
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "PROFILE_OR_BASE"


class StateCommands:
    def __init__(self, replies=None):
        self.replies = replies or {}
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.replies.get(message)


class Handler:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.name


class Delegate:
    def __init__(self, reply="UNIVERSAL_FALLBACK"):
        self.reply = reply
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


def build_stack(*, registered=True, step="MAIN_MENU", state_replies=None):
    base = BaseConversation(registered=registered, step=step)
    commands = StateCommands(state_replies)
    handlers = {
        "JOB": Handler("JOB_FLOW"),
        "PRODUCT": Handler("PRODUCT_FLOW"),
        "SERVICE": Handler("SERVICE_FLOW"),
        "RIDE": Handler("RIDE_FLOW"),
        "EVENT": Handler("EVENT_FLOW"),
        "APPOINTMENT": Handler("APPOINTMENT_FLOW"),
    }
    delegate = Delegate()
    orchestrator = NaturalConversationOrchestrator(
        delegate=delegate,
        category_brain=UniversalCategoryFlowBrain(),
        handlers=handlers,
    )
    app = EndToEndAppFlowService(
        orchestrator,
        base_conversation=base,
        response_commands=commands,
    )
    return app, base, commands, handlers, delegate


def test_fresh_user_onboarding_beats_every_domain_handler():
    app, base, commands, handlers, delegate = build_stack(registered=False, step="START")
    response = app.process("u1", "need 3 workers for warehouse")
    assert "Choose your language" in response
    assert not commands.calls
    assert all(not handler.calls for handler in handlers.values())
    assert not delegate.calls


def test_legacy_capability_step_migrates_without_old_role_menu():
    app, base, commands, handlers, delegate = build_stack(registered=True, step="WAITING_CAPABILITIES")
    response = app.process("u1", "seller and buyer")
    assert "PODX" in response
    assert "profile" in response.lower() or "ప్రొఫైల్" in response
    assert all(not handler.calls for handler in handlers.values())
    assert not delegate.calls


def test_active_buyer_doubt_beats_product_category_routing():
    msg = "Warranty ఉందా?"
    app, base, commands, handlers, delegate = build_stack(state_replies={msg: "BUYER_DOUBT_RELAY"})
    assert app.process("buyer", msg) == "BUYER_DOUBT_RELAY"
    assert commands.calls == [("buyer", msg)]
    assert all(not handler.calls for handler in handlers.values())
    assert not delegate.calls


def test_active_seller_answer_beats_generic_missing_field_or_category_logic():
    msg = "1 year warranty ఉంది"
    app, base, commands, handlers, delegate = build_stack(state_replies={msg: "SELLER_ANSWER_RELAY"})
    assert app.process("seller", msg) == "SELLER_ANSWER_RELAY"
    assert commands.calls == [("seller", msg)]
    assert all(not handler.calls for handler in handlers.values())


def test_cross_category_reference_app_behaviour_matrix_routes_only_one_runtime():
    cases = [
        ("need 3 workers for warehouse", "JOB", "JOB_FLOW"),
        ("55 inch TV కావాలి", "PRODUCT", "PRODUCT_FLOW"),
        ("AC repair కావాలి", "SERVICE", "SERVICE_FLOW"),
        ("airportకి వెళ్లాలి cab కావాలి", "RIDE", "RIDE_FLOW"),
        ("రేపు Hyderabad వెళ్తున్నాను carలో 3 seats ఉన్నాయి", "RIDE", "RIDE_FLOW"),
        ("doctor appointment కావాలి", "APPOINTMENT", "APPOINTMENT_FLOW"),
        ("wedding function planning కావాలి", "EVENT", "EVENT_FLOW"),
    ]
    for message, expected_key, expected_reply in cases:
        app, base, commands, handlers, delegate = build_stack()
        assert app.process("u1", message) == expected_reply
        assert len(handlers[expected_key].calls) == 1
        assert sum(len(h.calls) for h in handlers.values()) == 1
        assert not delegate.calls


def test_unsupported_verticals_fall_back_safely_instead_of_wrong_handler():
    for message in (
        "medicine కావాలి",
        "2BHK flat rent కావాలి",
        "hotel room booking కావాలి",
        "100 bags cement quotation కావాలి",
    ):
        app, base, commands, handlers, delegate = build_stack()
        assert app.process("u1", message) == "UNIVERSAL_FALLBACK"
        assert all(not handler.calls for handler in handlers.values())
        assert len(delegate.calls) == 1


def test_registered_start_state_can_reach_normal_welcome_or_delegate_path():
    app, base, commands, handlers, delegate = build_stack(registered=True, step="START")
    assert app.process("u1", "Hi") == "UNIVERSAL_FALLBACK"
    assert not base.calls
    assert len(delegate.calls) == 1


def test_sequence_can_switch_domains_after_state_is_resolved_without_sticky_handler():
    app, base, commands, handlers, delegate = build_stack()
    assert app.process("u1", "job కావాలి") == "JOB_FLOW"
    assert app.process("u1", "AC repair కావాలి") == "SERVICE_FLOW"
    assert app.process("u1", "cab కావాలి") == "RIDE_FLOW"
    assert len(handlers["JOB"].calls) == 1
    assert len(handlers["SERVICE"].calls) == 1
    assert len(handlers["RIDE"].calls) == 1
