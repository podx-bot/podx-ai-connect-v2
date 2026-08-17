from app.services.universal_product_schema_service import UniversalProductSchemaService


def test_ai_schema_controls_valid_units_and_attributes_without_product_hardcoding():
    service = UniversalProductSchemaService(
        schema_classifier=lambda subject: {
            "valid_units": ["bag", "kg"],
            "key_attributes": ["grade", "brand"],
            "optional_attributes": ["manufacture_date"],
            "buyer_questions": ["price", "grade", "brand", "delivery_or_pickup"],
            "seller_fields": ["price", "grade", "brand", "availability", "delivery_or_pickup"],
            "quantity_required": True,
            "price_required": True,
            "confidence": 0.95,
        }
    )

    schema = service.schema_for("some construction material")
    assert schema["valid_units"] == ["bag", "kg"]
    assert "grade" in schema["key_attributes"]
    assert service.validate_unit("some construction material", "bag") is True
    assert service.validate_unit("some construction material", "litre") is False


def test_different_subject_can_receive_completely_different_unit_model():
    def classifier(subject):
        if "display" in subject:
            return {
                "valid_units": ["piece"],
                "key_attributes": ["screen_size", "brand", "model", "resolution"],
                "buyer_questions": ["price", "screen_size", "warranty", "delivery_or_pickup"],
                "seller_fields": ["price", "screen_size", "model", "condition_or_quality", "availability"],
                "quantity_required": True,
                "price_required": True,
                "confidence": 0.93,
            }
        return {"valid_units": ["pack"], "confidence": 0.8}

    service = UniversalProductSchemaService(schema_classifier=classifier)
    schema = service.schema_for("home display device")

    assert schema["valid_units"] == ["piece"]
    assert "screen_size" in schema["key_attributes"]
    assert service.validate_unit("home display device", "kg") is False


def test_missing_fields_are_product_schema_driven_not_global_list():
    service = UniversalProductSchemaService(
        schema_classifier=lambda subject: {
            "valid_units": ["piece"],
            "seller_fields": ["price", "model", "availability"],
            "quantity_required": False,
            "price_required": True,
            "confidence": 0.9,
        }
    )

    missing = service.relevant_missing_fields("device", {"rate": 1000, "model": "X1"})
    assert missing == ["availability"]
    assert "quantity" not in missing


def test_ai_failure_has_safe_generic_fallback():
    def broken(subject):
        raise RuntimeError("provider unavailable")

    service = UniversalProductSchemaService(schema_classifier=broken)
    schema = service.schema_for("unknown future product")

    assert schema["valid_units"]
    assert "price" in schema["seller_fields"]
    assert schema["confidence"] < 0.5
