from app.services.deal_discussion_service import DealDiscussionService


class _Schema:
    def __init__(self, schema):
        self.schema = schema

    def schema_for(self, subject):
        return dict(self.schema)

    def validate_unit(self, subject, unit):
        return str(unit).casefold() in {str(x).casefold() for x in self.schema["valid_units"]}

    def relevant_missing_fields(self, subject, details):
        missing = []
        if self.schema.get("quantity_required") and details.get("quantity") is None:
            missing.append("quantity")
        if self.schema.get("price_required") and details.get("rate") is None and details.get("price") is None:
            missing.append("price")
        if "delivery_or_pickup" in self.schema.get("seller_fields", []) and not details.get("fulfilment"):
            missing.append("delivery_or_pickup")
        return missing

    def extract_details(self, subject, text):
        return {}


def _service(schema):
    return DealDiscussionService(None, None, lambda user_id: {}, product_schema_service=_Schema(schema))


def test_cement_schema_prompt_uses_only_schema_units():
    service = _service({
        "valid_units": ["bag", "kg"],
        "key_attributes": ["brand", "grade"],
        "seller_fields": ["price", "availability", "delivery_or_pickup"],
        "quantity_required": True,
        "price_required": True,
        "confidence": 0.98,
    })
    prompt = service._seller_prompt({"domain": "PRODUCT", "subject": "construction material"}, {})
    assert "bag, kg" in prompt
    assert "litre" not in prompt
    assert "brand" in prompt and "grade" in prompt


def test_tv_schema_rejects_weight_unit_and_does_not_prompt_for_kg():
    service = _service({
        "valid_units": ["piece"],
        "key_attributes": ["screen_size", "brand", "model"],
        "seller_fields": ["price", "availability", "delivery_or_pickup"],
        "quantity_required": True,
        "price_required": True,
        "confidence": 0.99,
    })
    request = {"domain": "PRODUCT", "subject": "smart television"}
    prompt = service._seller_prompt(request, {})
    assert "piece" in prompt
    assert "kg" not in prompt
    reply = service._invalid_product_unit(request, {"quantity": 1, "unit": "kg"})
    assert reply is not None
    assert "piece" in reply


def test_schema_missing_fields_respects_product_semantics():
    service = _service({
        "valid_units": ["piece"],
        "key_attributes": ["screen_size"],
        "seller_fields": ["price", "delivery_or_pickup"],
        "quantity_required": True,
        "price_required": True,
        "confidence": 0.95,
    })
    request = {"domain": "PRODUCT", "subject": "display device", "quantity": 1, "unit": "piece"}
    missing = service._missing_required(request, {"rate": 25000, "fulfilment": "pickup"}, "25000 pickup")
    assert missing == []
