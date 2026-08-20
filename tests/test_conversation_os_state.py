from app.repositories.conversation_turn_ledger_repository import ConversationTurnLedgerRepository
from app.services.conversation_state_merge_engine import ConversationStateMergeEngine
from app.services.conversation_topic_resolver import ConversationTopicResolver


def test_turn_ledger_persists_channel_neutral_state_and_history(tmp_path):
    repo = ConversationTurnLedgerRepository(str(tmp_path / "podx.db"))
    state = {
        "goal": "BUY",
        "active_flow": "PRODUCT_BUY",
        "active_entity": "chicken",
        "known_fields": {"quantity": 10, "unit": "kg"},
        "missing_fields": ["variant"],
        "pending_action": "match_seller",
        "last_bot_message": "10 kg chickenకి seller match దొరికింది.",
        "last_bot_intent": "MATCH_FOUND",
        "expected_reply_type": "free_text_update",
        "last_user_message": "నాకు 10 కేజీల చికెన్ కావాలి",
    }
    repo.save_state("buyer-1", state, channel="whatsapp")
    turn_id = repo.append_turn(
        "buyer-1",
        channel="whatsapp",
        user_message="నాకు 10 కేజీల చికెన్ కావాలి",
        bot_message=state["last_bot_message"],
        turn_kind="NEW_REQUEST",
        resolved_meaning="buy 10 kg chicken",
        next_action="match_seller",
        confidence=0.97,
        state=state,
    )
    assert turn_id > 0
    loaded = repo.load_state("buyer-1")
    assert loaded["known_fields"]["quantity"] == 10
    assert loaded["active_entity"] == "chicken"
    recent = repo.recent_turns("buyer-1")
    assert recent[0]["turn_kind"] == "NEW_REQUEST"
    assert recent[0]["state"]["known_fields"]["unit"] == "kg"


def test_merge_preserves_known_fields_and_latest_explicit_value_wins():
    merge = ConversationStateMergeEngine()
    state = {
        "goal": "BUY",
        "active_entity": "chicken",
        "known_fields": {"quantity": 10, "unit": "kg", "variant": "with bone"},
        "missing_fields": [],
    }
    updated = merge.merge_state(state, {"known_fields": {"variant": "boneless", "quantity": None}})
    assert updated["known_fields"]["quantity"] == 10
    assert updated["known_fields"]["unit"] == "kg"
    assert updated["known_fields"]["variant"] == "boneless"

    changed_again = merge.apply_explicit_change(updated, quantity=5)
    assert changed_again["known_fields"]["quantity"] == 5
    assert changed_again["known_fields"]["variant"] == "boneless"


def test_topic_resolver_keeps_short_variant_inside_active_chicken_context():
    resolver = ConversationTopicResolver()
    assert resolver.resolve("chicken", "బోన్లెస్ కావాలి") == "CONTINUE"
    assert resolver.resolve("chicken", "రేట్ ఎంత?") == "CONTINUE"


def test_topic_resolver_detects_explicit_different_subject():
    resolver = ConversationTopicResolver()
    assert resolver.resolve("chicken", "నాకు electrician కావాలి", {"subject": "electrician"}) == "NEW_TOPIC"
