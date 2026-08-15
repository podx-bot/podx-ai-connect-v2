from app.repositories.grocery_rfq_repository import GroceryRFQRepository
from app.repositories.product_catalog_repository import ProductCatalogRepository


def test_candidate_sellers_rank_by_basket_overlap(tmp_path):
    db_path = str(tmp_path / "podx.db")
    repo = GroceryRFQRepository(db_path)
    catalog = ProductCatalogRepository(db_path)
    catalog.upsert_product("seller-1", "rice", stock_status="IN_STOCK")
    catalog.upsert_product("seller-1", "oil", stock_status="IN_STOCK")
    catalog.upsert_product("seller-2", "rice", stock_status="IN_STOCK")

    sellers = repo.find_candidate_sellers([
        {"item_name": "rice"},
        {"item_name": "oil"},
    ])

    assert sellers[0]["seller_user_id"] == "seller-1"
    assert sellers[0]["matched_items"] >= sellers[1]["matched_items"]
