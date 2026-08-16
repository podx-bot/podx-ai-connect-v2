"""Bridge provider catalogs into the universal RFQ engine."""
from __future__ import annotations

from typing import Any, Dict, List


class UniversalCatalogRFQService:
    def __init__(self, catalog_repository, rfq_repository) -> None:
        self.catalog = catalog_repository
        self.rfqs = rfq_repository

    def refresh_legacy_catalogs(self) -> Dict[str, int]:
        return self.catalog.import_legacy_catalogs()

    def target_rfq(self, rfq_id: int, limit: int = 30) -> Dict[str, Any]:
        rfq = self.rfqs.get_rfq(int(rfq_id))
        if not rfq:
            return {"status": "RFQ_NOT_FOUND", "rfq_id": int(rfq_id), "targets": []}
        items = self.rfqs.list_items(int(rfq_id))
        matches = self.catalog.match_providers(str(rfq.get("rfq_type") or "OTHER"), items, limit=limit)
        targets: List[Dict[str, Any]] = []
        for match in matches:
            score = float(match.get("match_percent") or 0) / 100.0
            created = self.rfqs.add_target(
                int(rfq_id),
                str(match["provider_user_id"]),
                match_score=score,
            )
            targets.append({**match, "target_created": bool(created), "match_score": round(score, 4)})
        return {
            "status": "TARGETED" if targets else "NO_MATCH",
            "rfq_id": int(rfq_id),
            "rfq_type": rfq.get("rfq_type"),
            "targets": targets,
        }

    def sync_and_target(self, rfq_id: int, limit: int = 30) -> Dict[str, Any]:
        imported = self.refresh_legacy_catalogs()
        result = self.target_rfq(rfq_id, limit=limit)
        result["legacy_imported"] = imported
        return result
