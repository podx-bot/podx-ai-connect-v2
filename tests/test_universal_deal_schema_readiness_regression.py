from app.services.universal_product_schema_service import UniversalProductSchemaService


def test_tv_like_lump_sum_offer_does_not_ask_quantity_or_internal_fields():
    service = UniversalProductSchemaService(
        schema_classifier=lambda subject: {
            "valid_units": ["piece"],
            "key_attributes": ["brand", "screen_size", "model", "testing_available"],
            "seller_fields": [
                "price",
                "condition",
                "working_status",
                "model",
                "included_accessories",
                "delivery_or_pickup",
                "testing_available",
            ],
            "quantity_required": True,
            "price_required": True,
            "confidence": 0.96,
        }
    )

    missing = service.relevant_missing_fields(
        "55 inch Samsung Smart TV",
        {
            "rate": 42000,
            "fulfilment": "delivery",
            "attributes": {
                "condition": "new",
                "working_status": "fully working",
                "model": "UA55",
                "included_accessories": "remote and stand",
                "brand": "Samsung",
                "screen_size": "55 inch",
            },
        },
    )

    assert missing == []
