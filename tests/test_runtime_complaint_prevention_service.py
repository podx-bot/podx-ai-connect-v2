from app.services.runtime_complaint_prevention_service import RuntimeComplaintPreventionService


class Stub:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def process(self, sender_mobile, message):
        self.calls.append((sender_mobile, message))
        if self.replies:
            return self.replies.pop(0)
        return None


class BrainResult:
    category = "SUPPORT"


class Brain:
    def classify(self, message):
        return BrainResult()


class Obs:
    def __init__(self):
        self.rows = []

    def record(self, *args, **kwargs):
        self.rows.append((args, kwargs))
        return len(self.rows)


def test_empty_reply_is_never_silently_dropped():
    obs = Obs()
    guard = RuntimeComplaintPreventionService(Stub([None]), Brain(), obs)

    reply = guard.process("u1", "help")

    assert "request save" in reply
    assert "unresolved" in reply
    assert obs.rows[-1][0][3] == "NO_SILENT_DROP"


def test_normal_business_reply_passes_through_unchanged():
    guard = RuntimeComplaintPreventionService(Stub(["1 year warranty ఉంది"]), Brain())
    assert guard.process("u1", "Warranty ఉందా?") == "1 year warranty ఉంది"


def test_three_repeated_unresolved_prompts_break_the_bot_loop():
    repeated = "మీ request అర్థం చేసుకోవడానికి ఇంకొంచెం detail కావాలి. చెప్పండి"
    guard = RuntimeComplaintPreventionService(Stub([repeated, repeated, repeated]), Brain())

    assert guard.process("u1", "x") == repeated
    assert guard.process("u1", "x") == repeated
    third = guard.process("u1", "x")

    assert "repeat చేయను" in third
    assert "human support" in third


def test_different_replies_do_not_trigger_false_loop_detection():
    guard = RuntimeComplaintPreventionService(
        Stub(["quantity చెప్పండి", "price చెప్పండి", "delivery location చెప్పండి"]), Brain()
    )

    assert guard.process("u1", "a") == "quantity చెప్పండి"
    assert guard.process("u1", "b") == "price చెప్పండి"
    assert guard.process("u1", "c") == "delivery location చెప్పండి"


def test_loop_state_is_isolated_per_user():
    repeated = "need more detail"
    guard = RuntimeComplaintPreventionService(Stub([repeated] * 4), Brain())

    assert guard.process("u1", "x") == repeated
    assert guard.process("u1", "x") == repeated
    assert guard.process("u2", "x") == repeated
    assert guard.process("u2", "x") == repeated
