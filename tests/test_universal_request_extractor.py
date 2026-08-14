from types import SimpleNamespace

from app.services.universal_request_extractor import UniversalRequestExtractor


class FakeInteractions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.outputs.pop(0))


class FakeClient:
    def __init__(self, outputs):
        self.interactions = FakeInteractions(outputs)


def test_extracts_unknown_worker_need_without_fixed_category_list():
    client = FakeClient([
        '{"side":"NEED","domain":"WORKERS","subject":"marble polishing workers",'
        '"quantity":2,"unit":"people","price":null,"currency":null,'
        '"when_text":"tomorrow","location_text":null,"location_required":true,'
        '"constraints":[],"confidence":0.96}'
    ])
    extractor = UniversalRequestExtractor(client=client)

    result = extractor.extract("రేపు ఇద్దరు marble polishing వాళ్లు కావాలి")

    assert result["success"] is True
    request = result["request"]
    assert request["side"] == "NEED"
    assert request["domain"] == "WORKERS"
    assert request["subject"] == "marble polishing workers"
    assert request["quantity"] == 2.0
    assert request["location_required"] is True


def test_extracts_free_form_service_offer():
    client = FakeClient([
        "```json\n"
        '{"side":"OFFER","domain":"SERVICE","subject":"solar inverter repair",'
        '"quantity":null,"unit":null,"price":null,"currency":null,'
        '"when_text":"weekends","location_text":"Guntur","location_required":false,'
        '"constraints":["home visits"],"confidence":0.91}'
        "\n```"
    ])
    extractor = UniversalRequestExtractor(client=client)

    result = extractor.extract("I repair solar inverters in Guntur, home visits on weekends")

    request = result["request"]
    assert request["side"] == "OFFER"
    assert request["domain"] == "SERVICE"
    assert request["subject"] == "solar inverter repair"
    assert request["location_text"] == "Guntur"
    assert request["location_required"] is False
    assert request["constraints"] == ["home visits"]


def test_extracts_product_need_with_price_quantity_and_unit():
    client = FakeClient([
        '{"side":"NEED","domain":"PRODUCT","subject":"8mm copper wire",'
        '"quantity":"3","unit":"rolls","price":"2400", "currency":"inr",'
        '"when_text":null,"location_text":null,"location_required":true,'
        '"constraints":["8mm"],"confidence":1.2}'
    ])
    extractor = UniversalRequestExtractor(client=client)

    result = extractor.extract("Need three rolls of 8mm copper wire under ₹2400")

    request = result["request"]
    assert request["quantity"] == 3.0
    assert request["unit"] == "rolls"
    assert request["price"] == 2400.0
    assert request["currency"] == "INR"
    assert request["confidence"] == 1.0


def test_prompt_explicitly_preserves_unknown_future_subjects():
    prompt = UniversalRequestExtractor._build_prompt("some future request")

    assert "fixed profession/product/category list" in prompt
    assert "do not reject unknown occupations, products, or services" in prompt
    assert "User message: some future request" in prompt


def test_invalid_model_shape_fails_safely_without_inventing_data():
    client = FakeClient([
        '{"side":"MAYBE","domain":"PRODUCT","subject":"something",'
        '"quantity":null,"unit":null,"price":null,"currency":null,'
        '"when_text":null,"location_text":null,"location_required":true,'
        '"constraints":[],"confidence":0.5}'
    ])
    extractor = UniversalRequestExtractor(client=client)

    result = extractor.extract("ambiguous request")

    assert result["success"] is False
    assert result["status"] == "EXTRACTION_ERROR"
    assert result["request"] is None


def test_no_ai_key_returns_explicit_not_configured_status():
    extractor = UniversalRequestExtractor(api_key="", client=None)

    result = extractor.extract("Need something")

    assert result == {
        "success": False,
        "status": "AI_NOT_CONFIGURED",
        "request": None,
    }
