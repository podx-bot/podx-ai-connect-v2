from app.services.intent_router_service import IntentRouterService


class _Interaction:
    output_text = "SERVICE"


class _Interactions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _Interaction()


class _Client:
    def __init__(self):
        self.interactions = _Interactions()


def test_immediate_duplicate_ambiguous_classification_reuses_result():
    router = IntentRouterService(api_key="")
    router._client = _Client()

    first = router.classify("దగ్గరలో ఎవరో వచ్చి పని చేయాలి")
    second = router.classify("దగ్గరలో ఎవరో వచ్చి పని చేయాలి")

    assert first["intent"] == "SERVICE"
    assert second == first
    assert router._client.interactions.calls == 1


def test_different_message_does_not_reuse_previous_ai_result():
    router = IntentRouterService(api_key="")
    router._client = _Client()

    router.classify("దగ్గరలో ఎవరో వచ్చి పని చేయాలి")
    router.classify("ఇంకొక వేరే అవసరం ఉంది")

    assert router._client.interactions.calls == 2
