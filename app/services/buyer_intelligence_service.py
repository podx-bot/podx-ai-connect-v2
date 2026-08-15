"""PODX Buyer Intelligence Layer.

Produces explainable buying guidance without inventing live online prices. Fresh
online/local offers are supplied by adapters later; payment remains separate.
"""
from __future__ import annotations
from typing import Any, Dict, List

class BuyerIntelligenceService:
    def build_buying_guide(self, subject: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        c=context or {}
        return {
            "subject": str(subject).strip(),
            "questions": [
                "ఎందుకు కొనాలి / main use ఏమిటి?", "ఎవరు వాడతారు?", "ఎంత usage/quantity కావాలి?",
                "Budget range ఎంత?", "Must-have features ఏవి?", "ఎంత త్వరగా కావాలి?",
            ],
            "decision_framework": ["WHAT_TO_BUY","WHY","QUALITY_CHECK","HOW_MUCH","FAIR_PRICE","WHEN_TO_BUY","WHERE_TO_BUY","LOCAL_VS_ONLINE"],
            "context": c,
        }

    def compare_offers(self, local_offers: List[Dict[str, Any]], online_offers: List[Dict[str, Any]], urgency: str = "NORMAL") -> Dict[str, Any]:
        offers=[]
        for channel, rows in (("LOCAL",local_offers),("ONLINE",online_offers)):
            for row in rows:
                item=dict(row); item["channel"]=channel; item["value_score"]=self._score(item,urgency); offers.append(item)
        ranked=sorted(offers,key=lambda x:(-x["value_score"],float(x.get("price") or 10**15)))
        best=ranked[0] if ranked else None
        return {"best":best,"ranked":ranked,"recommendation":self._recommend(best),"rule":"Cheapest is not automatically best; compare exact variant, freshness, warranty, returns, delivery and service."}

    def price_watch_decision(self, current_price: float | None, target_price: float | None, exact_variant: bool, freshness_minutes: int | None) -> Dict[str, Any]:
        if current_price is None:return {"status":"NO_FRESH_PRICE","action":"VERIFY_PRICE"}
        if not exact_variant:return {"status":"VARIANT_MISMATCH","action":"DO_NOT_COMPARE"}
        if freshness_minutes is None or freshness_minutes>1440:return {"status":"STALE_PRICE","action":"REFRESH_PRICE"}
        if target_price is not None and float(current_price)<=float(target_price):return {"status":"TARGET_REACHED","action":"NOTIFY"}
        return {"status":"WATCHING","action":"WAIT"}

    @staticmethod
    def _score(o: Dict[str, Any], urgency: str) -> float:
        # Explainable 0-100 heuristic; missing facts do not receive bonus points.
        score=50.0
        if o.get("warranty"):score+=10
        if o.get("returns"):score+=8
        if o.get("verified_seller"):score+=8
        if o.get("service_available"):score+=7
        if o.get("exact_variant"):score+=7
        delivery=o.get("delivery_minutes")
        if delivery is not None:
            try:
                d=float(delivery); score += 10 if d<=60 and str(urgency).upper()=="URGENT" else (5 if d<=1440 else 0)
            except:pass
        return max(0.0,min(100.0,score))

    @staticmethod
    def _recommend(best: Dict[str, Any] | None) -> str:
        if not best:return "Need fresh comparable offers before recommending."
        channel=best.get("channel")
        return "BUY_LOCAL" if channel=="LOCAL" else "BUY_ONLINE"
