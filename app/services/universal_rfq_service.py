"""Domain-neutral RFQ comparison and selection logic."""
from __future__ import annotations

from typing import Any, Dict, List


class UniversalRFQService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def compare_quotes(self, rfq_id: int) -> Dict[str, Any]:
        rfq = self.repository.get_rfq(rfq_id)
        if not rfq:
            return {"status": "RFQ_NOT_FOUND", "rfq_id": int(rfq_id), "quotes": []}
        requested = self.repository.list_items(rfq_id)
        required = [item for item in requested if int(item.get("required") or 0) == 1]
        required_ids = {int(item["id"]): item for item in required}
        rows = []
        for quote in self.repository.submitted_quotes(rfq_id):
            available_required = set()
            missing = []
            calculated_total = 0.0
            quote_by_item = {int(item["rfq_item_id"]): item for item in quote.get("items") or []}
            for item_id, requested_item in required_ids.items():
                quoted = quote_by_item.get(item_id)
                if quoted and int(quoted.get("available") or 0) == 1 and int(quoted.get("included") or 0) == 1:
                    available_required.add(item_id)
                    calculated_total += self._line_total(requested_item, quoted)
                else:
                    missing.append(str(requested_item.get("item_name") or "Item"))
            for item in requested:
                if int(item.get("required") or 0) == 1:
                    continue
                quoted = quote_by_item.get(int(item["id"]))
                if quoted and int(quoted.get("available") or 0) == 1 and int(quoted.get("included") or 0) == 1:
                    calculated_total += self._line_total(item, quoted)
            calculated_total += float(quote.get("service_fee") or 0) + float(quote.get("delivery_fee") or 0)
            provider_total = quote.get("provider_total")
            total = float(provider_total) if provider_total is not None else calculated_total
            coverage = (len(available_required) / len(required_ids)) if required_ids else 1.0
            rows.append(
                {
                    "quote_id": int(quote["id"]),
                    "provider_user_id": str(quote["provider_user_id"]),
                    "coverage": round(coverage, 4),
                    "coverage_percent": round(coverage * 100, 1),
                    "available_required_items": len(available_required),
                    "required_items": len(required_ids),
                    "missing_items": missing,
                    "total": round(total, 2),
                    "service_fee": float(quote.get("service_fee") or 0),
                    "delivery_fee": float(quote.get("delivery_fee") or 0),
                    "reliability_score": float(quote.get("reliability_score") or 0.5),
                    "notes": quote.get("notes"),
                }
            )
        rows.sort(key=lambda row: (-row["coverage"], row["total"], -row["reliability_score"], row["provider_user_id"]))
        for index, row in enumerate(rows):
            row["rank"] = index + 1
            row["label"] = self._label(row, rows)
        return {"status": "OK", "rfq_id": int(rfq_id), "rfq_type": rfq.get("rfq_type"), "quotes": rows}

    def select_quote(self, rfq_id: int, quote_id: int, requester_user_id: str) -> Dict[str, Any]:
        comparison = self.compare_quotes(rfq_id)
        if comparison.get("status") != "OK":
            return comparison
        selected = next((row for row in comparison["quotes"] if int(row["quote_id"]) == int(quote_id)), None)
        if selected is None:
            return {"status": "QUOTE_NOT_FOUND", "rfq_id": int(rfq_id), "quote_id": int(quote_id)}
        if not self.repository.select_quote(rfq_id, quote_id, requester_user_id):
            return {"status": "NOT_SELECTABLE", "rfq_id": int(rfq_id), "quote_id": int(quote_id)}
        return {"status": "SELECTED", "rfq_id": int(rfq_id), **selected}

    @staticmethod
    def _line_total(requested: Dict[str, Any], quoted: Dict[str, Any]) -> float:
        if quoted.get("line_total") is not None:
            return float(quoted.get("line_total") or 0)
        if quoted.get("unit_price") is None:
            return 0.0
        quantity = requested.get("quantity")
        return float(quoted.get("unit_price") or 0) * (float(quantity) if quantity is not None else 1.0)

    @staticmethod
    def _label(row: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return ""
        full = [item for item in rows if item["coverage"] >= 1.0]
        if row["rank"] == 1:
            return "BEST_MATCH"
        if full and row["coverage"] >= 1.0 and row["total"] == min(item["total"] for item in full):
            return "LOWEST_FULL_MATCH_PRICE"
        if row["coverage"] < 1.0:
            return "PARTIAL_MATCH"
        return "FULL_MATCH"
