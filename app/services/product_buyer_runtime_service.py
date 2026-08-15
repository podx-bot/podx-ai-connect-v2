"""Runtime bridge: matched product -> Product AI Desk -> RAG -> Buyer Intelligence -> Decision Engine.

This service is intentionally deterministic and evidence-first. Seller-specific live
facts (price/stock/offer) stay on the fresh catalog path; RAG can answer stable
seller-confirmed details and FAQs without bypassing freshness safeguards.
"""
from __future__ import annotations
from typing import Any, Dict


class ProductBuyerRuntimeService:
    DECISION_WORDS = (
        "should i buy", "worth", "best", "recommend", "compare", "buy or not",
        "కొనాలా", "కొనవచ్చా", "మంచిదా", "బెస్ట్", "సరైనదా", "తీసుకోవాలా",
        "खरीदूं", "अच्छा है", "बेस्ट", "सिफारिश",
    )

    def __init__(
        self,
        notification_repository,
        demand_repository,
        catalog_repository,
        product_desk,
        rag_service,
        buyer_intelligence,
        decision_service,
    ) -> None:
        self.notifications = notification_repository
        self.demands = demand_repository
        self.catalog = catalog_repository
        self.product_desk = product_desk
        self.rag = rag_service
        self.buyer_intelligence = buyer_intelligence
        self.decision_service = decision_service

    def evaluate(self, sender_mobile: str, message: str) -> Dict[str, Any] | None:
        """Build one explainable runtime packet for the buyer's latest matched product."""
        if not hasattr(self.notifications, "latest_interest_for_buyer"):
            return None
        interest = self.notifications.latest_interest_for_buyer(str(sender_mobile))
        if not interest:
            return None

        request = self.demands.get(int(interest["request_id"]))
        if not request or str(request.get("domain") or "").upper() != "PRODUCT":
            return None

        subject = str(request.get("subject") or "Product").strip()
        seller_user_id = str(interest.get("responder_user_id") or "").strip()
        if not seller_user_id:
            return None

        product = self.catalog.find_active(seller_user_id, subject)
        if not product:
            return None

        question = str(message or "").strip()
        desk_result = self.product_desk.answer(product, question)
        rag_context = self.rag.retrieve_context(
            question,
            namespaces=["SELLER_FAQ", "SELLER_PRODUCT", "PODX_PRODUCT"],
            owner_user_id=seller_user_id,
            subject=subject,
            limit=5,
        )
        buyer_guide = self.buyer_intelligence.build_buying_guide(
            subject,
            {
                "request_id": int(interest["request_id"]),
                "seller_user_id": seller_user_id,
                "seller_status": str(interest.get("requester_status") or "PENDING").upper(),
            },
        )
        option = self._decision_option(product, interest)
        decision = self.decision_service.decide(
            {"intent": "product_buy", "goal": "BUY_SMART", "subject": subject},
            [option],
        )
        return {
            "subject": subject,
            "seller_user_id": seller_user_id,
            "product": product,
            "desk": desk_result,
            "rag": rag_context,
            "buyer_guide": buyer_guide,
            "decision": decision,
        }

    def process(self, sender_mobile: str, message: str) -> str | None:
        packet = self.evaluate(sender_mobile, message)
        if packet is None:
            return None

        desk = packet["desk"]
        rag = packet["rag"]
        answer = str(desk.get("answer") or "").strip()

        # For stable unknown details, RAG may prevent an unnecessary seller escalation.
        # Never use historical RAG evidence to answer live-sensitive price/stock/offer questions.
        if desk.get("status") == "ASK_SELLER_ONCE" and not rag.get("live_verification_required"):
            evidence = rag.get("evidence") or []
            if evidence:
                answer = str(evidence[0].get("content") or answer).strip()

        if not answer:
            return None

        if self._is_decision_question(message):
            answer = self._append_decision_guidance(answer, packet)
        return answer

    @classmethod
    def _is_decision_question(cls, message: str) -> bool:
        text = " ".join(str(message or "").casefold().split())
        return any(word in text for word in cls.DECISION_WORDS)

    @staticmethod
    def _decision_option(product: Dict[str, Any], interest: Dict[str, Any]) -> Dict[str, Any]:
        features = product.get("features") or []
        return {
            "id": product.get("id"),
            "subject": product.get("subject"),
            "price": product.get("price"),
            "verified": True,
            "quality_ok": bool(features),
            "service_available": bool(product.get("delivery_available")),
            "best_value": bool(features) and product.get("price") is not None,
            "seller_confirmed": True,
            "seller_status": str(interest.get("requester_status") or "PENDING").upper(),
        }

    @staticmethod
    def _append_decision_guidance(answer: str, packet: Dict[str, Any]) -> str:
        product = packet["product"]
        guide = packet["buyer_guide"]
        decision = packet["decision"]
        checks = []
        if product.get("variant"):
            checks.append("exact variant")
        if product.get("features"):
            checks.append("required features")
        checks.extend(["warranty/returns", "final fresh price & stock"])
        compact_checks = ", ".join(dict.fromkeys(checks))
        score = None
        if decision.get("best"):
            score = decision["best"].get("decision_score")
        score_text = f" Current option score: {score:.0f}/100." if isinstance(score, (int, float)) else ""
        framework = guide.get("decision_framework") or []
        framework_text = " → ".join(str(x) for x in framework[:4])
        return (
            f"{answer}\n\n🤖 PODX Buyer Intelligence: seller-confirmed local option available.{score_text} "
            f"Final choice ముందు {compact_checks} verify చేయండి."
            + (f"\nDecision path: {framework_text}." if framework_text else "")
        )
