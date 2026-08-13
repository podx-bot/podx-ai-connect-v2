from app.database.database import Database
from app.repositories.demand_repository import DemandRepository
from app.services.demand_capture_service import DemandCaptureService


def build_service(tmp_path):
    database = Database(str(tmp_path / "demand.db"))
    repository = DemandRepository(database)
    return database, repository, DemandCaptureService(repository)


def test_unresolved_demand_is_persisted_with_structured_fields(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        demand = service.capture_unresolved(
            user_mobile="9199",
            intent="SHOP_PRODUCT",
            category="Helmet",
            location_text="Vijayawada",
            source_message="1500 లోపు helmet కావాలి",
            structured_fields={"budget_max": 1500, "product": "helmet"},
        )

        assert demand["status"] == "OPEN"
        assert demand["category"] == "Helmet"
        assert demand["structured_fields"]["budget_max"] == 1500
        assert repository.list_open()[0]["id"] == demand["id"]
    finally:
        database.close()


def test_admin_summary_clusters_repeated_local_demand(tmp_path):
    database, _, service = build_service(tmp_path)
    try:
        for mobile in ("9101", "9102", "9103"):
            service.capture_unresolved(
                user_mobile=mobile,
                intent="SHOP_PRODUCT",
                category="Helmet",
                location_text="Vijayawada",
                source_message="helmet కావాలి",
            )
        service.capture_unresolved(
            user_mobile="9104",
            intent="SERVICE",
            category="Plumber",
            location_text="Vijayawada",
            source_message="plumber కావాలి",
        )

        summary = service.admin_summary()

        assert summary["open_count"] == 4
        assert summary["action_required"] is True
        assert summary["top_clusters"][0]["demand_key"] == "Helmet"
        assert summary["top_clusters"][0]["demand_count"] == 3
    finally:
        database.close()


def test_demand_can_move_from_open_to_matched_to_resolved(tmp_path):
    database, repository, service = build_service(tmp_path)
    try:
        demand = service.capture_unresolved(
            user_mobile="9199",
            intent="SERVICE",
            category="Plumber",
            source_message="plumber కావాలి",
        )

        matched = service.mark_matched(demand["id"], "PROVIDER", "provider:42")
        assert matched["status"] == "MATCHED"
        assert matched["resolution_ref"] == "provider:42"
        assert repository.list_open() == []

        resolved = service.mark_resolved(demand["id"], "PROVIDER", "provider:42")
        assert resolved["status"] == "RESOLVED"
        assert resolved["resolved_at"] is not None
    finally:
        database.close()
