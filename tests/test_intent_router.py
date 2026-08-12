from app.services.intent_router_service import IntentRouterService


def test_router_recognizes_job_seeker_without_ai_call():
    router = IntentRouterService(api_key="")
    result = router.classify("నాకు పని కావాలి")
    assert result["intent"] == "JOB_SEEKER"
    assert result["source"] == "rules"


def test_router_recognizes_employer_without_menu_number():
    router = IntentRouterService(api_key="")
    result = router.classify("రేపటికి 3 workers కావాలి")
    assert result["intent"] == "EMPLOYER"


def test_router_recognizes_appointment_future_module():
    router = IntentRouterService(api_key="")
    result = router.classify("రేపు salon appointment కావాలి")
    assert result["intent"] == "APPOINTMENT"


def test_router_recognizes_local_service_future_module():
    router = IntentRouterService(api_key="")
    result = router.classify("nearby electrician కావాలి")
    assert result["intent"] == "SERVICE"
