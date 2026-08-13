from typing import Any


class DemandCaptureService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def capture_unresolved(
        self,
        *,
        user_mobile: str,
        intent: str,
        source_message: str,
        category: str | None = None,
        location_text: str | None = None,
        structured_fields: dict[str, Any] | None = None,
    ) -> dict:
        return self.repository.create(
            user_mobile=user_mobile,
            intent=intent,
            category=category,
            location_text=location_text,
            source_message=source_message,
            structured_fields=structured_fields or {},
            status="OPEN",
        )

    def mark_matched(self, demand_id: int, resolution_type: str, resolution_ref: str) -> dict | None:
        return self.repository.update_status(
            demand_id,
            "MATCHED",
            resolution_type=resolution_type,
            resolution_ref=resolution_ref,
        )

    def mark_resolved(self, demand_id: int, resolution_type: str, resolution_ref: str) -> dict | None:
        return self.repository.update_status(
            demand_id,
            "RESOLVED",
            resolution_type=resolution_type,
            resolution_ref=resolution_ref,
        )

    def admin_summary(self, limit: int = 10) -> dict:
        open_demands = self.repository.list_open(limit=500)
        clusters = self.repository.top_open_clusters(limit=limit)
        return {
            "open_count": len(open_demands),
            "top_clusters": clusters,
            "action_required": bool(open_demands),
        }
