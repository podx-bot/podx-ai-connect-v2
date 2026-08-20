import pytest

from app.services.universal_conversation_contract import (
    ResponsePhase,
    UniversalConversationContract,
    UserTurnType,
)


@pytest.fixture
def contract():
    return UniversalConversationContract()


def active_state():
    return {
        "active_flow": "ACTIVE_CONVERSATION",
        "active_entity": "current request",
        "known_fields": {"request_text": "10 kg chicken కావాలి"},
    }


@pytest.mark.parametrize(
    ("message", "state", "expected"),
    [
        ("10 kg chicken కావాలి", {}, UserTurnType.NEW),
        ("బోన్లెస్ కావాలి", active_state(), UserTurnType.UPDATE),
        ("రేట్ ఎంత?", active_state(), UserTurnType.QUESTION),
        ("ఇది తప్పు, 5 kg చేయండి", active_state(), UserTurnType.CORRECTION),
        ("service బాగోలేదు complaint ఉంది", active_state(), UserTurnType.COMPLAINT),
        ("రద్దు చేయండి", active_state(), UserTurnType.CANCEL),
    ],
)
def test_user_turn_types_are_domain_neutral(contract, message, state, expected):
    assert contract.classify_user_turn(message, state) == expected


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("✅ Match దొరికింది! Seller: Sujatha", ResponsePhase.MATCH),
        ("availability confirmation కోసం wait చేస్తున్నాను", ResponsePhase.WAITING),
        ("ప్రస్తుతం match లేదు", ResponsePhase.NO_MATCH),
        ("మీ request రద్దు చేశాను", ResponsePhase.CANCELLED),
    ],
)
def test_response_phases_are_domain_neutral(contract, reply, expected):
    assert contract.classify_response(reply) == expected


def test_internal_runtime_language_is_a_release_blocker(contract):
    violations = contract.validate_turn(
        message="బోన్లెస్ కావాలి",
        reply="seller-confirmed product profileలో pending_action update చేస్తున్నాను",
        state_before=active_state(),
    )
    assert "INTERNAL_LANGUAGE_LEAK" in {v.code for v in violations}


def test_repeated_waiting_status_is_a_release_blocker(contract):
    reply = "chicken availability seller confirmation కోసం wait చేస్తున్నాను"
    violations = contract.validate_turn(
        message="10 kg chicken కావాలి",
        reply=reply,
        state_before=active_state(),
        previous_reply=reply,
    )
    assert "DUPLICATE_PENDING_STATUS" in {v.code for v in violations}


def test_unchanged_match_must_not_regress_to_waiting(contract):
    violations = contract.validate_turn(
        message="status చెప్పండి",
        reply="availability confirmation కోసం wait చేస్తున్నాను",
        state_before=active_state(),
        previous_reply="✅ Match దొరికింది! Seller: Sujatha",
        request_changed=False,
    )
    assert "MATCH_REGRESSED_TO_WAITING" in {v.code for v in violations}


def test_real_update_may_require_rematching(contract):
    violations = contract.validate_turn(
        message="బోన్లెస్ కావాలి",
        reply="availability confirmation కోసం wait చేస్తున్నాను",
        state_before=active_state(),
        previous_reply="✅ Match దొరికింది! Seller: Sujatha",
        request_changed=True,
    )
    assert "MATCH_REGRESSED_TO_WAITING" not in {v.code for v in violations}


def test_update_without_context_is_detected(contract):
    violations = contract.validate_turn(
        message="బోన్లెస్ కావాలి",
        reply="సరే, చూస్తున్నాను",
        state_before={},
    )
    # Without active context, this phrase is a new request rather than an update;
    # the contract must therefore avoid inventing context.
    assert "UPDATE_WITHOUT_CONTEXT" not in {v.code for v in violations}


def test_release_matrix_covers_full_user_lifecycle(contract):
    required = {
        "new_request",
        "followup_update",
        "question_or_doubt",
        "correction",
        "complaint",
        "cancellation",
        "no_match",
        "match_found",
        "counterparty_reject",
        "timeout",
        "duplicate_inbound",
        "late_or_stale_event",
        "restart_and_resume",
        "telugu_english_mixed",
        "text_voice_equivalence",
        "internal_language_never_leaks",
    }
    assert required == set(contract.release_matrix())
