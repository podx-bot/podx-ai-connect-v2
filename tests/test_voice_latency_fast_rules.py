from app.services.intent_router_service import IntentRouterService


def test_rule_router_ignores_podx_wake_word_before_clear_service_request():
    assert IntentRouterService._classify_rules("Hi PODX, నాకు Electrician కావాలి") == "SERVICE"


def test_rule_router_handles_common_telugu_stt_electrician_variant():
    assert IntentRouterService._classify_rules("హాయ్ ప్రోడక్స్ నాకు ఎలక్ట్రీషన్ కావాలి") == "SERVICE"


def test_rule_router_keeps_service_provider_priority_over_customer_stem():
    assert IntentRouterService._classify_rules("నేను electrician service చేస్తాను") == "SERVICE_PROVIDER"
