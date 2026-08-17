"""Runtime bridge: matched product -> Product AI Desk -> RAG -> Buyer Intelligence -> Decision Engine."""
from __future__ import annotations
import os
from typing import Any, Dict

from app.repositories.business_customer_desk_repository import BusinessCustomerDeskRepository
from app.repositories.hybrid_support_repository import HybridSupportRepository
from app.repositories.product_pricelist_pending_repository import ProductPriceListPendingRepository
from app.repositories.reengagement_repository import ReengagementRepository
from app.repositories.street_vendor_repository import StreetVendorRepository
from app.services.business_customer_desk_service import BusinessCustomerDeskService
from app.services.hybrid_support_service import HybridSupportService
from app.services.product_pricelist_ai_service import ProductPriceListAIService
from app.services.smart_reengagement_service import SmartReengagementService
from app.services.street_vendor_proximity_service import StreetVendorProximityService
from app.services.universal_context_router import UniversalContextRouter


class ProductBuyerRuntimeService:
    PRODUCT_QUERY_WORDS = (
        "?", "price", "rate", "ధర", "రేట్", "ఎంత", "stock", "available", "availability", "ఉందా", "దొరుకుతుందా",
        "delivery", "డెలివరీ", "warranty", "return", "expiry", "feature", "features", "details", "spec", "original",
        "brand", "model", "variant", "size", "weight", "quantity", "color", "colour", "video", "demo", "quality",
        "कीमत", "स्टॉक", "डिलीवरी", "वारंटी", "फीचर", "मॉडल",
    )
    DECISION_WORDS = (
        "should i buy", "worth", "best", "recommend", "compare", "buy or not", "కొనాలా", "కొనవచ్చా", "మంచిదా",
        "బెస్ట్", "సరైనదా", "తీసుకోవాలా", "खरीदूं", "अच्छा है", "बेस्ट", "सिफारिश",
    )

    def __init__(self, notification_repository, demand_repository, catalog_repository, product_desk, rag_service,
                 buyer_intelligence, decision_service, seller_escalation=None, user_repository=None,
                 price_list_ai=None, whatsapp_service=None, reengagement_service=None, hybrid_support=None,
                 street_vendor_runtime=None, business_desk_runtime=None, context_router=None) -> None:
        self.notifications = notification_repository
        self.demands = demand_repository
        self.catalog = catalog_repository
        self.product_desk = product_desk
        self.rag = rag_service
        self.buyer_intelligence = buyer_intelligence
        self.decision_service = decision_service
        self.seller_escalation = seller_escalation
        self.context_router = context_router or UniversalContextRouter()
        db_path = getattr(catalog_repository, "db_path", "podx.db")
        effective_whatsapp = whatsapp_service or getattr(seller_escalation, "whatsapp", None)
        contact_resolver = getattr(seller_escalation, "contact_resolver", None)
        self.hybrid_support = hybrid_support
        if self.hybrid_support is None and effective_whatsapp is not None and contact_resolver is not None and getattr(rag_service, "repository", None) is not None:
            self.hybrid_support = HybridSupportService(
                repository=HybridSupportRepository(db_path),
                rag_repository=rag_service.repository,
                whatsapp_service=effective_whatsapp,
                contact_resolver=contact_resolver,
            )
        self.reengagement = reengagement_service
        if self.reengagement is None and user_repository is not None and effective_whatsapp is not None:
            self.reengagement = SmartReengagementService(
                demand_repository=demand_repository,
                catalog_repository=catalog_repository,
                user_repository=user_repository,
                reengagement_repository=ReengagementRepository(db_path),
                whatsapp_service=effective_whatsapp,
            )
        self.price_list_ai = price_list_ai or ProductPriceListAIService(
            api_key=str(os.getenv("GEMINI_API_KEY") or ""),
            catalog_repository=catalog_repository,
            pending_repository=ProductPriceListPendingRepository(db_path),
            user_repository=user_repository,
            reengagement_service=self.reengagement,
        )
        self.street_vendor_runtime = street_vendor_runtime
        if self.street_vendor_runtime is None and user_repository is not None and effective_whatsapp is not None:
            self.street_vendor_runtime = StreetVendorProximityService(
                repository=StreetVendorRepository(db_path),
                demand_repository=demand_repository,
                user_repository=user_repository,
                whatsapp_service=effective_whatsapp,
                radius_km=float(os.getenv("PODX_VENDOR_ALERT_RADIUS_KM") or "1.5"),
            )
        self.business_desk_runtime = business_desk_runtime
        if self.business_desk_runtime is None and effective_whatsapp is not None and getattr(rag_service, "repository", None) is not None:
            self.business_desk_runtime = BusinessCustomerDeskService(
                repository=BusinessCustomerDeskRepository(db_path),
                rag_repository=rag_service.repository,
                whatsapp_service=effective_whatsapp,
                user_repository=user_repository,
            )

    def evaluate(self, sender_mobile: str, message: str) -> Dict[str, Any] | None:
        if not hasattr(self.notifications, "latest_interest_for_buyer"):
            return None
        interest = self.notifications.latest_interest_for_buyer(str(sender_mobile))
        if not interest:
            return None
        request = self.demands.get(int(interest["request_id"]))
        if not request or str(request.get("domain") or "").upper() != "PRODUCT":
            return None
        try:
            if self.context_router.introduces_new_subject(request, str(message or "")):
                return None
        except Exception:
            pass
        subject = str(request.get("subject") or "Product").strip()
        seller_user_id = str(interest.get("responder_user_id") or "").strip()
        if not seller_user_id:
            return None
        product = self.catalog.find_active(seller_user_id, subject)
        if not product:
            return None
        question = str(message or "").strip()
        desk_result = self.product_desk.answer(product, question)
        rag_context = self.rag.retrieve_context(question, namespaces=["SELLER_FAQ", "SELLER_PRODUCT", "PODX_PRODUCT"],
                                                owner_user_id=seller_user_id, subject=subject, limit=5)
        buyer_guide = self.buyer_intelligence.build_buying_guide(subject, {
            "request_id": int(interest["request_id"]), "seller_user_id": seller_user_id,
            "seller_status": str(interest.get("requester_status") or "PENDING").upper(),
        })
        option = self._decision_option(product, interest)
        decision = self.decision_service.decide({"intent": "product_buy", "goal": "BUY_SMART", "subject": subject}, [option])
        return {"subject": subject, "seller_user_id": seller_user_id, "product": product, "desk": desk_result,
                "rag": rag_context, "buyer_guide": buyer_guide, "decision": decision}

    def process(self, sender_mobile: str, message: str) -> str | None:
        if self.business_desk_runtime is not None:
            business_reply = self.business_desk_runtime.process_text(sender_mobile, message)
            if business_reply is not None:
                return business_reply
        if self.street_vendor_runtime is not None:
            vendor_reply = self.street_vendor_runtime.process_text(sender_mobile, message)
            if vendor_reply is not None:
                return vendor_reply
        price_list_reply = self.price_list_ai.process_text(sender_mobile, message) if self.price_list_ai is not None else None
        if price_list_reply is not None:
            return price_list_reply
        if not self._looks_like_product_question(message):
            return None
        packet = self.evaluate(sender_mobile, message)
        if packet is None:
            return None
        desk, rag = packet["desk"], packet["rag"]
        answer = str(desk.get("answer") or "").strip()
        if desk.get("status") == "ASK_SELLER_ONCE" and not rag.get("live_verification_required"):
            evidence = rag.get("evidence") or []
            if evidence:
                answer = str(evidence[0].get("content") or answer).strip()
            elif self.seller_escalation is not None:
                escalation = self.seller_escalation.escalate(sender_mobile, desk, packet["subject"])
                if escalation.get("created"):
                    answer = "🤖 ఈ detail నా seller-confirmed knowledgeలో లేదు. Sellerని ఒక్కసారి అడిగాను; answer వచ్చిన వెంటనే మీకు పంపిస్తాను."
                else:
                    answer = "⏳ ఇదే question sellerకి ఇప్పటికే పంపాను. Answer వచ్చిన వెంటనే మీకు పంపిస్తాను."
        elif desk.get("status") == "ASK_SELLER_ONCE" and self.seller_escalation is not None:
            escalation = self.seller_escalation.escalate(sender_mobile, desk, packet["subject"])
            answer = "🤖 Current detail seller నుంచి fresh confirmation కావాలి. Sellerని అడిగాను; confirm అయిన వెంటనే మీకు పంపిస్తాను." if escalation.get("created") else "⏳ Fresh confirmation కోసం seller reply wait చేస్తున్నాను."
        if not answer:
            return None
        if self._is_decision_question(message):
            answer = self._append_decision_guidance(answer, packet)
        return answer

    @classmethod
    def _looks_like_product_question(cls, message: str) -> bool:
        text = " ".join(str(message or "").casefold().split())
        return any(word in text for word in cls.PRODUCT_QUERY_WORDS) or any(word in text for word in cls.DECISION_WORDS)

    @classmethod
    def _is_decision_question(cls, message: str) -> bool:
        text = " ".join(str(message or "").casefold().split())
        return any(word in text for word in cls.DECISION_WORDS)

    @staticmethod
    def _decision_option(product: Dict[str, Any], interest: Dict[str, Any]) -> Dict[str, Any]:
        features = product.get("features") or []
        return {"id": product.get("id"), "subject": product.get("subject"), "price": product.get("price"), "verified": True,
                "quality_ok": bool(features), "service_available": bool(product.get("delivery_available")),
                "best_value": bool(features) and product.get("price") is not None, "seller_confirmed": True,
                "seller_status": str(interest.get("requester_status") or "PENDING").upper()}

    @staticmethod
    def _append_decision_guidance(answer: str, packet: Dict[str, Any]) -> str:
        product, guide, decision = packet["product"], packet["buyer_guide"], packet["decision"]
        checks = []
        if product.get("variant"): checks.append("exact variant")
        if product.get("features"): checks.append("required features")
        checks.extend(["warranty/returns", "final fresh price & stock"])
        compact_checks = ", ".join(dict.fromkeys(checks))
        score = decision.get("best", {}).get("decision_score") if decision.get("best") else None
        score_text = f" Current option score: {score:.0f}/100." if isinstance(score, (int, float)) else ""
        framework_text = " → ".join(str(x) for x in (guide.get("decision_framework") or [])[:4])
        return f"{answer}\n\n🤖 PODX Buyer Intelligence: seller-confirmed local option available.{score_text} Final choice ముందు {compact_checks} verify చేయండి." + (f"\nDecision path: {framework_text}." if framework_text else "")
