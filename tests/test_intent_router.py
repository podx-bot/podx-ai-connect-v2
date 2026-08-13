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


def test_router_recognizes_local_service_customer():
    router = IntentRouterService(api_key="")
    result = router.classify("nearby electrician కావాలి")
    assert result["intent"] == "SERVICE"


def test_router_recognizes_product_seller():
    router = IntentRouterService(api_key="")
    result = router.classify("నేను products అమ్ముతాను")
    assert result["intent"] == "SELL_PRODUCT"
    assert result["source"] == "rules"


def test_router_recognizes_service_provider_before_service_customer():
    router = IntentRouterService(api_key="")
    result = router.classify("నేను electrician service చేస్తాను")
    assert result["intent"] == "SERVICE_PROVIDER"
    assert result["source"] == "rules"


def test_router_recognizes_product_buyer_separately_from_seller():
    router = IntentRouterService(api_key="")
    result = router.classify("నాకు product కొనాలి price ఎంత")
    assert result["intent"] == "SHOP_PRODUCT"
