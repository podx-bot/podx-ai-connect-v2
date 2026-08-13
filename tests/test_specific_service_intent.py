from app.services.intent_router_service import IntentRouterService


def test_specific_service_phrases_route_without_generic_worker_menu():
    router = IntentRouterService(api_key="")

    phrases = (
        "నాకు electrician కావాలి",
        "నాకు ఎలక్ట్రీషన్ కావాలి",
        "electrican కావాలి",
        "నాకు alteration కావాలి",
        "బ్లౌజ్ అల్టరేషన్ కావాలి",
        "tailor కావాలి",
        "plumber కావాలి",
        "కార్పెంటర్ కావాలి",
    )

    for phrase in phrases:
        assert router.classify(phrase)["intent"] == "SERVICE"


def test_generic_worker_request_stays_employer():
    router = IntentRouterService(api_key="")
    assert router.classify("నాకు workers కావాలి")["intent"] == "EMPLOYER"


def test_driver_need_is_service_but_explicit_worker_request_is_employer():
    router = IntentRouterService(api_key="")
    assert router.classify("నాకు driver కావాలి")["intent"] == "SERVICE"
    assert router.classify("driver worker కావాలి")["intent"] == "EMPLOYER"
