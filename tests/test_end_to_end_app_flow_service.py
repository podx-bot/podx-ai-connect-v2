from app.services.end_to_end_app_flow_service import EndToEndAppFlowService


class Step:
    def __init__(self, name):
        self.name = name


class Session:
    def __init__(self, name):
        self.step = Step(name)


class Sessions:
    def __init__(self, name="MAIN_MENU"):
        self.name = name

    def get(self, sender):
        return Session(self.name)


class Users:
    def __init__(self, user=None):
        self.user = user

    def find_by_whatsapp_mobile(self, sender):
        return self.user


class Base:
    def __init__(self, user=None, step="MAIN_MENU"):
        self.user_repository = Users(user)
        self.session_registry = Sessions(step)
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return "PROFILE_FLOW"


class Commands:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def process_text(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


class Inner:
    def __init__(self, base, commands, reply="INNER_FLOW"):
        self.base_conversation = base
        self.response_commands = commands
        self.reply = reply
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        return self.reply


def test_fresh_user_profile_flow_wins_before_every_runtime():
    base = Base(user=None, step="START")
    commands = Commands(reply="SHOULD_NOT_RUN")
    flow = EndToEndAppFlowService(Inner(base, commands))

    assert flow.process("u", "Hi") == "PROFILE_FLOW"
    assert commands.calls == []


def test_capability_selection_remains_in_profile_flow_after_registration_row_exists():
    base = Base(user={"registration_complete": 1}, step="WAITING_CAPABILITIES")
    commands = Commands(reply="SHOULD_NOT_RUN")
    flow = EndToEndAppFlowService(Inner(base, commands))

    assert flow.process("u", "1,2,5") == "PROFILE_FLOW"
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
