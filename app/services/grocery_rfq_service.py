"""Rank grocery/kirana quotations for Best Value / Lowest Price / Top sellers."""
from __future__ import annotations
from typing import Any, Dict, List


class GroceryRFQService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def rank(self, rfq_id: int, top_n: int = 5) -> Dict[str, Any]:
        required = self.repository.list_items(rfq_id)
        required_ids = {int(item["id"]) for item in required}
        quotes = self.repository.submitted_quotes(rfq_id)
        scored: List[Dict[str, Any]] = []
        for quote in quotes:
            available_rows = [row for row in quote.get("items") or [] if int(row.get("available") or 0) == 1 and row.get("price") is not None]
            covered = {int(row["rfq_item_id"]) for row in available_rows}
            coverage = (len(covered & required_ids) / len(required_ids)) if required_ids else 0.0
            subtotal = sum(float(row.get("price") or 0) for row in available_rows)
            delivery_fee = float(quote.get("delivery_fee") or 0)
            total = subtotal + delivery_fee
            rating = max(0.0, min(float(quote.get("rating") or 0) / 5.0, 1.0))
            reliability = max(0.0, min(float(quote.get("reliability_score") or 0.5), 1.0))
            distance = float(quote.get("distance_km") or 999)
            distance_score = 1.0 / (1.0 + max(distance, 0.0))
            scored.append({**quote, "coverage": coverage, "subtotal": subtotal, "total": total, "distance_score": distance_score, "rating_score": rating, "reliability": reliability})

        valid_totals = [row["total"] for row in scored if row["total"] > 0]
        cheapest = min(valid_totals) if valid_totals else None
        for row in scored:
            price_score = (cheapest / row["total"]) if cheapest and row["total"] > 0 else 0.0
            row["best_value_score"] = round(
                row["coverage"] * 0.40
                + price_score * 0.30
                + row["rating_score"] * 0.12
                + row["reliability"] * 0.10
                + row["distance_score"] * 0.08,
                4,
            )

        top = sorted(scored, key=lambda row: (row["best_value_score"], row["coverage"], -row["total"]), reverse=True)[: max(1, int(top_n))]
        lowest = min(scored, key=lambda row: row["total"], default=None)
        best = top[0] if top else None
        return {"rfq_id": int(rfq_id), "best_value": best, "lowest_price": lowest, "top_sellers": top}

    def split_basket(self, rfq_id: int) -> Dict[str, Any]:
        """Choose cheapest available line per item; caller decides whether delivery overhead makes split worthwhile."""
        quotes = self.repository.submitted_quotes(rfq_id)
        best_by_item: Dict[int, Dict[str, Any]] = {}
        for quote in quotes:
            for item in quote.get("items") or []:
                if int(item.get("available") or 0) != 1 or item.get("price") is None:
                    continue
                item_id = int(item["rfq_item_id"])
                candidate = {"seller_user_id": quote["seller_user_id"], "quote_id": quote["id"], "item": item, "price": float(item["price"])}
                current = best_by_item.get(item_id)
                if current is None or candidate["price"] < current["price"]:
                    best_by_item[item_id] = candidate
        subtotal = sum(row["price"] for row in best_by_item.values())
        sellers = sorted({row["seller_user_id"] for row in best_by_item.values()})
        return {"rfq_id": int(rfq_id), "items": list(best_by_item.values()), "subtotal": subtotal, "seller_count": len(sellers), "sellers": sellers}
