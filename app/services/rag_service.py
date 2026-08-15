"""PODX Retrieval-Augmented Generation orchestration.

RAG retrieves trusted PODX/seller/official knowledge. Live prices and live stock
must come from fresh adapters, not historical knowledge. This service returns
context + evidence so an LLM/decision layer can answer without hallucinating.
"""
from __future__ import annotations
from typing import Any, Dict, List

class RagService:
    LIVE_SENSITIVE = ("price", "rate", "ధర", "రేట్", "stock", "available", "availability", "స్టాక్", "offer", "discount")

    def __init__(self, repository) -> None:
        self.repository = repository

    def retrieve_context(self, query: str, *, namespaces: List[str] | None = None, owner_user_id: str | None = None, subject: str | None = None, limit: int = 5) -> Dict[str, Any]:
        hits = self.repository.retrieve(query, namespaces=namespaces, owner_user_id=owner_user_id, subject=subject, limit=limit)
        evidence=[]
        for hit in hits:
            evidence.append({
                "id": hit.get("id"),
                "content": hit.get("content"),
                "source_type": hit.get("source_type"),
                "source_ref": hit.get("source_ref"),
                "trust_level": hit.get("trust_level"),
                "score": hit.get("retrieval_score"),
                "valid_until": hit.get("valid_until"),
                "metadata": hit.get("metadata") or {},
            })
        live_sensitive = any(word in str(query or "").casefold() for word in self.LIVE_SENSITIVE)
        return {
            "status": "CONTEXT_FOUND" if evidence else "NO_CONTEXT",
            "query": str(query or "").strip(),
            "subject": subject,
            "evidence": evidence,
            "live_verification_required": bool(live_sensitive),
            "answer_policy": "Use evidence only for factual claims. Current price/stock/offer requires fresh verification.",
        }

    def ingest_seller_product(self, product: Dict[str, Any]) -> List[int]:
        product_id = product.get("id")
        seller = str(product.get("seller_user_id") or "")
        subject = str(product.get("subject") or "Product")
        ids=[]
        facts=[]
        if product.get("brand"): facts.append(f"Brand: {product['brand']}")
        if product.get("variant"): facts.append(f"Variant: {product['variant']}")
        if product.get("quantity") is not None: facts.append(f"Quantity: {product['quantity']} {product.get('unit') or ''}".strip())
        if product.get("price") is not None: facts.append(f"Seller confirmed price: ₹{product['price']}")
        if product.get("stock_status"): facts.append(f"Stock status: {product['stock_status']}")
        if product.get("delivery_available"): facts.append("Delivery available")
        features=product.get("features") or []
        if features: facts.append("Features: " + "; ".join(str(x) for x in features))
        if facts:
            ids.append(self.repository.add("SELLER_PRODUCT", ". ".join(facts), owner_user_id=seller, subject=subject, source_type="SELLER_CONFIRMED", source_ref=f"product:{product_id}", metadata={"product_id": product_id}))
        return ids

    def ingest_faq(self, product_id: int, seller_user_id: str, subject: str, question: str, answer: str) -> int:
        content=f"Question: {str(question).strip()} Answer: {str(answer).strip()}"
        return self.repository.add("SELLER_FAQ", content, owner_user_id=str(seller_user_id), subject=str(subject), source_type="SELLER_CONFIRMED", source_ref=f"product:{int(product_id)}:faq")
