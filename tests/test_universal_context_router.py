from app.services.universal_context_router import UniversalContextRouter


def test_new_product_does_not_mutate_old_product_context():
    router = UniversalContextRouter()
    chicken = {"subject": "chicken", "domain": "PRODUCT"}

    assert router.introduces_new_subject(chicken, "5 kg rice bag కావాలి") is True
    assert router.introduces_new_subject(chicken, "5 kg rice bag 300rs only pickup sonarice") is True


def test_attribute_only_followup_stays_in_current_deal():
    router = UniversalContextRouter()
    chicken = {"subject": "fresh skinless chicken", "domain": "PRODUCT"}

    assert router.introduces_new_subject(chicken, "₹220 per kg delivery today") is False
    assert router.introduces_new_subject(chicken, "5 kg pickup") is False
    assert router.introduces_new_subject(chicken, "fresh skinless chicken ₹220 per kg delivery") is False


def test_compound_variant_containing_subject_stays_in_same_context():
    router = UniversalContextRouter()
    rice = {"subject": "rice", "domain": "PRODUCT"}

    assert router.introduces_new_subject(rice, "sonarice 300rs pickup") is False


def test_ai_semantic_classifier_is_source_of_truth_when_available():
    router = UniversalContextRouter(
        semantic_classifier=lambda request, text: {"new_subject": True}
    )
    assert router.introduces_new_subject({"subject": "anything"}, "rate 200") is True


def test_ai_failure_falls_back_without_breaking_deal_flow():
    def broken_classifier(request, text):
        raise RuntimeError("provider unavailable")

    router = UniversalContextRouter(semantic_classifier=broken_classifier)
    assert router.introduces_new_subject({"subject": "chicken"}, "₹220 per kg delivery") is False
