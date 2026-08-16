from app.repositories.catering_catalog_repository import CateringCatalogRepository
from app.repositories.product_catalog_repository import ProductCatalogRepository
from app.repositories.universal_catalog_repository import UniversalCatalogRepository
from app.repositories.universal_rfq_repository import UniversalRFQRepository
from app.services.universal_catalog_rfq_service import UniversalCatalogRFQService


def test_universal_catalog_matches_only_same_vertical(tmp_path):
    db = str(tmp_path / "catalog.db")
    catalog = UniversalCatalogRepository(db)
    catalog.upsert_item("caterer", "CATERING", "Chicken Biryani", category="Main", price=220)
    catalog.upsert_item("seller", "PRODUCT", "Chicken Biryani Pack", price=150)

    catering = catalog.match_providers("CATERING", ["Chicken Biryani"])
    assert [x["provider_user_id"] for x in catering] == ["caterer"]
    products = catalog.match_providers("PRODUCT", ["Chicken Biryani Pack"])
    assert [x["provider_user_id"] for x in products] == ["seller"]


def test_legacy_catering_and_product_catalogs_import_idempotently(tmp_path):
    db = str(tmp_path / "legacy.db")
    catering = CateringCatalogRepository(db)
    products = ProductCatalogRepository(db)
    catering.add_item("cat1", "Paneer Biryani", default_price=180, price_basis="plate")
    products.upsert_product("shop1", "Basmati Rice", brand="ABC", price=120, unit="kg")

    universal = UniversalCatalogRepository(db)
    first = universal.import_legacy_catalogs()
    second = universal.import_legacy_catalogs()

    assert first == {"CATERING": 1, "PRODUCT": 1}
    assert second == {"CATERING": 1, "PRODUCT": 1}
    assert len(universal.list_items("cat1", "CATERING")) == 1
    assert len(universal.list_items("shop1", "PRODUCT")) == 1


def test_rfq_targets_only_catalog_relevant_providers(tmp_path):
    db = str(tmp_path / "rfq.db")
    rfqs = UniversalRFQRepository(db)
    catalog = UniversalCatalogRepository(db)
    service = UniversalCatalogRFQService(catalog, rfqs)

    catalog.upsert_item("full", "CATERING", "Chicken Biryani")
    catalog.upsert_item("full", "CATERING", "Gulab Jamun")
    catalog.upsert_item("partial", "CATERING", "Chicken Biryani")
    catalog.upsert_item("wrong-type", "PRODUCT", "Chicken Biryani")

    rfq_id = rfqs.create_rfq(
        "customer",
        "CATERING",
        [
            {"item_name": "Chicken Biryani", "quantity": 100, "unit": "plates"},
            {"item_name": "Gulab Jamun", "quantity": 100, "unit": "pieces"},
        ],
        title="Birthday catering",
    )
    result = service.target_rfq(rfq_id)

    assert result["status"] == "TARGETED"
    assert [x["provider_user_id"] for x in result["targets"]] == ["full", "partial"]
    assert result["targets"][0]["match_percent"] == 100.0
    assert result["targets"][1]["match_percent"] == 50.0
    assert rfqs.target_for_provider("wrong-type", rfq_id) is None


def test_rfq_targeting_is_safe_to_retry(tmp_path):
    db = str(tmp_path / "retry.db")
    rfqs = UniversalRFQRepository(db)
    catalog = UniversalCatalogRepository(db)
    service = UniversalCatalogRFQService(catalog, rfqs)
    catalog.upsert_item("provider", "SERVICE", "AC Repair")
    rfq_id = rfqs.create_rfq("customer", "SERVICE", [{"item_name": "AC Repair"}])

    first = service.target_rfq(rfq_id)
    second = service.target_rfq(rfq_id)
    assert first["targets"][0]["target_created"] is True
    assert second["targets"][0]["target_created"] is False
    assert rfqs.target_for_provider("provider", rfq_id) is not None
