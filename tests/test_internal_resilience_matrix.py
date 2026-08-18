from app.services.domain_complaint_prevention_service import DomainComplaintPreventionService
from app.services.internal_resilience_matrix import InternalResilienceMatrix
from app.services.runtime_complaint_prevention_service import RuntimeComplaintPreventionService
from app.services.universal_category_flow_brain import UniversalCategoryFlowBrain


class Stub:
    def __init__(self, replies):
        self.replies = list(replies)

    def process(self, sender_mobile, message):
        return self.replies.pop(0) if self.replies else None


class FixedDecision:
    def __init__(self, category, side="SEEKER", action="FIND"):
        self.category = category
        self.side = side
        self.action = action


class FixedBrain:
    def __init__(self, category, side="SEEKER", action="FIND"):
        self.value = FixedDecision(category, side, action)

    def classify(self, message):
        return self.value


def test_resilience_matrix_is_complete_and_unique():
    assert InternalResilienceMatrix.validate() == []
    assert {
        "multi_turn_state_continuity",
        "multi_role_context_switch",
        "voice_text_parity",
        "restart_recovery",
        "bounded_escalation",
        "no_silent_drop",
        "commitment_boundary_guard",
    } <= InternalResilienceMatrix.keys()


def test_voice_transcript_and_typed_text_use_same_routing_contract():
    brain = UniversalCategoryFlowBrain()
    typed = brain.classify("airportకి వెళ్లాలి cab కావాలి")
    voice_transcript = brain.classify("  airportకి   వెళ్లాలి   cab కావాలి  ")
    assert (typed.category, typed.side, typed.action) == (
        voice_transcript.category,
        voice_transcript.side,
        voice_transcript.action,
    )


def test_same_user_can_switch_domains_without_permanent_role_lock():
    brain = UniversalCategoryFlowBrain()
    buyer = brain.classify("TV కొనాలి price చెప్పండి")
    employer = brain.classify("need 3 workers for warehouse")
    passenger = brain.classify("airportకి వెళ్లాలి cab కావాలి")

    assert (buyer.category, buyer.side) == ("COMMERCE", "SEEKER")
    assert (employer.category, employer.side) == ("JOBS", "PROVIDER")
    assert (passenger.category, passenger.side) == ("MOBILITY", "SEEKER")


def test_normal_follow_up_answer_is_not_rewritten_by_quality_guards():
    inner = DomainComplaintPreventionService(
        Stub(["1 year warranty ఉంది"]), FixedBrain("COMMERCE")
    )
    outer = RuntimeComplaintPreventionService(inner, FixedBrain("COMMERCE"))
    assert outer.process("seller1", "Warranty ఉందా?") == "1 year warranty ఉంది"


def test_restart_or_empty_lower_runtime_never_becomes_silent_drop():
    guard = RuntimeComplaintPreventionService(Stub([None]), FixedBrain("GENERAL"))
    reply = guard.process("u1", "continue my request")
    assert "request save" in reply
    assert "unresolved" in reply


def test_repeated_unresolved_flow_escalates_with_context_instead_of_looping():
    repeated = "need more detail"
    guard = RuntimeComplaintPreventionService(
        Stub([repeated, repeated, repeated]), FixedBrain("SUPPORT")
    )
    guard.process("u1", "same issue")
    guard.process("u1", "same issue")
    reply = guard.process("u1", "same issue")
    assert "human support" in reply
    assert "context" in reply


def test_commitment_boundary_guards_cover_core_verticals():
    cases = [
        ("COMMERCE", "Order confirmed", "availability"),
        ("SERVICES", "Booking confirmed", "scope"),
        ("FREELANCE", "Hire confirmed", "deliverables"),
        ("B2B_RFQ", "Here are the supplier quotes", "same specification / quantity / delivery basis"),
    ]
    for domain, raw, expected in cases:
        guard = DomainComplaintPreventionService(Stub([raw]), FixedBrain(domain))
        assert expected in guard.process("u1", "request")


def test_fare_change_requires_reconfirmation():
    guard = DomainComplaintPreventionService(
        Stub(["Fare changed from ₹300 to ₹350"]), FixedBrain("MOBILITY")
    )
    reply = guard.process("u1", "ride update")
    assert "Re-confirm" in reply
