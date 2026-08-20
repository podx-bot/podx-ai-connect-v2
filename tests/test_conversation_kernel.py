from app.services.conversation_kernel import ConversationKernel, ConversationState, TurnKind


def test_short_variant_followup_updates_active_product():
    kernel = ConversationKernel()
    state = ConversationState(
        user_id="buyer-1",
        goal="BUY",
        active_flow="PRODUCT_BUY",
        active_entity="chicken",
        known_fields={"subject": "chicken", "quantity": 10, "unit": "kg"},
        last_bot_message="10 kg chickenకి seller match దొరికింది.",
    )
    decision = kernel.resolve("buyer-1", "బోన్లెస్ కావాలి", state)
    assert decision.kind == TurnKind.UPDATE_EXISTING
    assert decision.next_action == "merge_active_state"
    assert decision.state.known_fields["quantity"] == 10


def test_short_quantity_followup_updates_active_product():
    kernel = ConversationKernel()
    state = ConversationState(user_id="buyer-1", active_entity="chicken")
    decision = kernel.resolve("buyer-1", "25 కేజీలు కావాలి", state)
    assert decision.kind == TurnKind.UPDATE_EXISTING
    assert decision.next_action == "merge_active_state"


def test_explicit_new_telugu_product_request_is_not_swallowed_by_active_context():
    kernel = ConversationKernel()
    state = ConversationState(user_id="buyer-1", active_entity="current request")
    decision = kernel.resolve("buyer-1", "నాకు 25 కేజీల బాస్మతి రైస్ కావాలి", state)
    assert decision.kind == TurnKind.NEW_REQUEST
    assert decision.next_action == "route_new_request"


def test_strong_long_change_message_stays_in_active_context():
    kernel = ConversationKernel()
    state = ConversationState(user_id="buyer-1", active_entity="chicken")
    decision = kernel.resolve("buyer-1", "rate 210 చేయండి, skinless కావాలి", state)
    assert decision.kind == TurnKind.UPDATE_EXISTING
    assert decision.next_action == "merge_active_state"


def test_yes_is_resolved_against_previous_expected_reply():
    kernel = ConversationKernel()
    state = ConversationState(
        user_id="buyer-1",
        active_entity="chicken",
        expected_reply_type="yes_no",
        pending_action="ask_seller_price",
        last_bot_message="Sellerని final rate అడగాలా?",
    )
    decision = kernel.resolve("buyer-1", "అవును", state)
    assert decision.kind == TurnKind.CONFIRMATION
    assert decision.resolved_meaning == "yes"
    assert decision.next_action == "ask_seller_price"


def test_question_stays_inside_active_context():
    kernel = ConversationKernel()
    state = ConversationState(user_id="buyer-1", active_entity="chicken")
    decision = kernel.resolve("buyer-1", "రేట్ ఎంత?", state)
    assert decision.kind == TurnKind.QUESTION
    assert decision.next_action == "answer_in_active_context"


def test_empty_reply_is_blocked_by_response_guard():
    kernel = ConversationKernel()
    decision = kernel.resolve("buyer-1", "hello")
    assert kernel.validate_reply(decision, "   ") is None
