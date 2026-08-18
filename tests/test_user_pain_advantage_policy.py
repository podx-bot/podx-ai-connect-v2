from app.services.user_pain_advantage_policy import UserPainAdvantagePolicy


CORE_DOMAINS = (
    "PROFILE",
    "JOBS",
    "COMMERCE",
    "SERVICES",
    "MOBILITY",
    "FREELANCE",
    "RFQ",
    "SUPPORT",
)


def test_every_core_domain_has_specific_pain_prevention_rules():
    assert UserPainAdvantagePolicy.validate_domains(CORE_DOMAINS) == {}


def test_global_rules_prevent_repeat_questions_wrong_role_dead_end_and_black_box():
    keys = UserPainAdvantagePolicy.rule_keys("COMMERCE")
    assert {
        "duplicate_questions",
        "wrong_role_routing",
        "bot_dead_end",
        "status_black_box",
    }.issubset(keys)


def test_jobs_prevents_irrelevant_matches_and_no_response_blackhole():
    keys = UserPainAdvantagePolicy.rule_keys("JOBS")
    assert "irrelevant_job_match" in keys
    assert "job_no_response_blackhole" in keys
    behaviours = UserPainAdvantagePolicy.required_behaviours("JOBS")
    assert {"RELEVANCE_RANKING", "ACTIVE_HOLD", "TARGET_WIDENING", "VISIBLE_STATUS"}.issubset(behaviours)


def test_commerce_contract_covers_live_doubt_and_delivery_failure_shapes():
    keys = UserPainAdvantagePolicy.rule_keys("COMMERCE")
    assert {"seller_no_response", "delivery_expectation_gap"}.issubset(keys)
    behaviours = UserPainAdvantagePolicy.required_behaviours("COMMERCE")
    assert {"DOUBT_RELAY", "PENDING_STATE", "DELIVERY_CONFIRM", "FINAL_SUMMARY"}.issubset(behaviours)


def test_services_requires_scope_price_basis_and_timing_confirmation():
    behaviours = UserPainAdvantagePolicy.required_behaviours("SERVICES")
    assert {"SCOPE_CONFIRM", "PRICE_BASIS", "TIME_CONFIRM"}.issubset(behaviours)


def test_mobility_prevents_hidden_price_changes_and_safety_uncertainty():
    keys = UserPainAdvantagePolicy.rule_keys("MOBILITY")
    assert {"hidden_ride_price_change", "ride_safety_uncertainty"}.issubset(keys)
    behaviours = UserPainAdvantagePolicy.required_behaviours("MOBILITY")
    assert {"FARE_BASIS", "RECONFIRM", "KYC_CONTEXT", "SAFE_CONTACT_EXCHANGE"}.issubset(behaviours)


def test_freelance_and_rfq_prevent_scope_comparison_ambiguity():
    assert "project_scope_ambiguity" in UserPainAdvantagePolicy.rule_keys("FREELANCE")
    assert "quote_apples_oranges" in UserPainAdvantagePolicy.rule_keys("RFQ")
    assert "NORMALIZED_SCOPE" in UserPainAdvantagePolicy.required_behaviours("RFQ")


def test_support_never_loops_forever_without_escalation():
    keys = UserPainAdvantagePolicy.rule_keys("SUPPORT")
    assert "support_loop_without_resolution" in keys
    behaviours = UserPainAdvantagePolicy.required_behaviours("SUPPORT")
    assert {"ATTEMPT_LIMIT", "CONTEXT_PRESERVATION", "HUMAN_ESCALATION"}.issubset(behaviours)


def test_unknown_domain_gets_global_safety_contract_but_fails_core_validation():
    keys = UserPainAdvantagePolicy.rule_keys("NEW_VERTICAL")
    assert "bot_dead_end" in keys
    assert UserPainAdvantagePolicy.validate_domains(("NEW_VERTICAL",)) == {
        "NEW_VERTICAL": ["missing_domain_specific_rule"]
    }
