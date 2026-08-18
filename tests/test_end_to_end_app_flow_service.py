from app.models.session import ConversationStep
from app.services.end_to_end_app_flow_service import EndToEndAppFlowService


class Session:
    def __init__(self, name):
        self.step = ConversationStep[name]
        self.data = {}


class Sessions:
    def __init__(self, name="MAIN_MENU"):
        self.session = Session(name)
        self.saved = []

    def get(self, sender):
        return self.session

    def save(self, sender):
        self.saved.append(sender)


class Users:
    def __init__(self, user=None):
        self.user = user
        self.registrations = []

    def find_by_whatsapp_mobile(self, sender):
        return self.user

    def create_or_update_registration(self, **kwargs):
        self.registrations.append(kwargs)
        self.user = {
            "registration_complete": 1,
            "language": kwargs["language"],
            "name": kwargs["name"],
            "area": kwargs["area"],
            "entered_mobile": kwargs["entered_mobile"],
        }


class Base:
    def __init__(self, user=None, step="MAIN_MENU"):
        self.user_repository = Users(user)
        self.session_registry = Sessions(step)
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "LEGACY_PROFILE_FLOW"


class Commands:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


class Inner:
    def __init__(self, base=None, commands=None, reply="INNER_FLOW"):
        if base is not None:
            self.base_conversation = base
        if commands is not None:
            self.response_commands = commands
        self.reply = reply
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


def test_fresh_user_starts_with_language_not_mobile_or_role_menu():
    base = Base(user=None, step="START")
    commands = Commands(reply="SHOULD_NOT_RUN")
    flow = EndToEndAppFlowService(Inner(base, commands))

    reply = flow.process("919876543210", "Hi")

    assert "1. తెలుగు" in reply
    assert "2. English" in reply
    assert "3. हिंदी" in reply
    assert "10 అంకెల" not in reply
    assert "Buy products" not in reply
    assert base.session_registry.session.step == ConversationStep.WAITING_LANGUAGE
    assert commands.calls == []


def test_registration_uses_whatsapp_sender_number_and_finishes_without_capability_selection():
    base = Base(user=None, step="START")
    flow = EndToEndAppFlowService(Inner(base, Commands(reply=None)))

    flow.process("919876543210", "Hi")
    assert flow.process("919876543210", "2") == "What is your name?"
    assert flow.process("919876543210", "Manohar") == "Tell me your area or town."
    reply = flow.process("919876543210", "Vuyyuru")

    assert "profile is ready" in reply
    assert base.session_registry.session.step == ConversationStep.MAIN_MENU
    assert base.user_repository.registrations == [{
        "whatsapp_mobile": "919876543210",
        "entered_mobile": "919876543210",
        "name": "Manohar",
        "language": "English",
        "area": "Vuyyuru",
    }]


def test_legacy_capability_step_is_retired_for_completed_profile():
    base = Base(user={"registration_complete": 1, "language": "Telugu"}, step="WAITING_CAPABILITIES")
    commands = Commands(reply="SHOULD_NOT_RUN")
    flow = EndToEndAppFlowService(Inner(base, commands))

    reply = flow.process("u", "1,2,5")

    assert "ప్రొఫైల్ సిద్ధమైంది" in reply
    assert base.session_registry.session.step == ConversationStep.MAIN_MENU
    assert commands.calls == []


def test_active_deal_state_wins_before_category_runtime():
    base = Base(user={"registration_complete": 1}, step="MAIN_MENU")
    commands = Commands(reply="BUYER_DOUBT_RELAY")
    inner = Inner(base, commands, reply="RIDE_OR_PRODUCT_FLOW")
    flow = EndToEndAppFlowService(inner)

    assert flow.process("buyer", "Warranty ఉందా?") == "BUYER_DOUBT_RELAY"
    assert inner.calls == []


def test_no_active_state_falls_through_to_universal_category_brain():
    base = Base(user={"registration_complete": 1}, step="MAIN_MENU")
    commands = Commands(reply=None)
    inner = Inner(base, commands, reply="UNIVERSAL_FLOW")
    flow = EndToEndAppFlowService(inner)

    assert flow.process("u", "రేపు Hyderabad వెళ్తున్నాను 3 seats ఉన్నాయి") == "UNIVERSAL_FLOW"
    assert len(inner.calls) == 1


def test_registered_start_state_is_not_forced_back_into_registration():
    base = Base(user={"registration_complete": 1}, step="START")
    commands = Commands(reply=None)
    flow = EndToEndAppFlowService(Inner(base, commands, reply="WELCOME_BACK"))

    assert flow.process("u", "Hi") == "WELCOME_BACK"


def test_composed_wrapper_can_use_explicit_profile_and_state_dependencies():
    base = Base(user={"registration_complete": 1}, step="MAIN_MENU")
    commands = Commands(reply="STATE_FIRST")
    composed = Inner(reply="ADMIN_OR_CATEGORY")
    flow = EndToEndAppFlowService(
        composed,
        base_conversation=base,
        response_commands=commands,
    )

    assert flow.process("buyer", "Warranty ఉందా?") == "STATE_FIRST"
    assert composed.calls == []


def test_explicit_profile_dependency_uses_v2_for_fresh_user():
    base = Base(user=None, step="START")
    commands = Commands(reply="SHOULD_NOT_RUN")
    composed = Inner(reply="SHOULD_NOT_RUN")
    flow = EndToEndAppFlowService(
        composed,
        base_conversation=base,
        response_commands=commands,
    )

    reply = flow.process("new-user", "Hi")
    assert "Choose your language" in reply
    assert commands.calls == []
    assert composed.calls == []
