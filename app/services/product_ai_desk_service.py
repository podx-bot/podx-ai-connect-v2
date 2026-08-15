"""Seller workload-reduction Product AI Desk.

Answers only from seller-confirmed catalog/FAQ data. Unknown seller-specific facts
are escalated rather than guessed. Designed for text or transcribed voice queries.
"""
from __future__ import annotations
import re
from typing import Any, Dict


class ProductAIDeskService:
    PRICE_WORDS = ("price", "rate", "ధర", "రేట్", "ఎంత", "कीमत")
    STOCK_WORDS = ("stock", "available", "availability", "ఉందా", "స్టాక్", "मिलेगा")
    DELIVERY_WORDS = ("delivery", "డెలివరీ", "home delivery", "डिलीवरी")
    VIDEO_WORDS = ("video", "demo", "వీడియో", "డెమో", "वीडियो")
    FEATURES_WORDS = ("feature", "details", "spec", "ఫీచర్", "డీటెయిల్స్", "వివరాలు")

    def __init__(self, catalog_repository) -> None:
        self.catalog = catalog_repository

    def answer(self, product: Dict[str, Any], question: str) -> Dict[str, Any]:
        text = " ".join(str(question or "").casefold().split())
        product_id = int(product["id"])
        direct = self.catalog.get_faq(product_id, text)
        if direct:
            return {"status": "ANSWERED", "answer": direct, "source": "SELLER_FAQ"}

        if self._contains(text, self.PRICE_WORDS):
            if product.get("price") is not None:
                return {"status": "ANSWERED", "answer": f"Seller confirmed price ₹{self._money(product['price'])}.", "source": "CATALOG"}
            return self._escalate("price", "ఈ product final price ఎంత?", product)

        if self._contains(text, self.STOCK_WORDS):
            stock = str(product.get("stock_status") or "UNKNOWN").upper()
            if stock == "IN_STOCK":
                return {"status": "ANSWERED", "answer": "Seller ఈ product stockలో ఉందని confirm చేశారు.", "source": "CATALOG"}
            if stock == "OUT_OF_STOCK":
                return {"status": "ANSWERED", "answer": "Seller ప్రకారం ప్రస్తుతం stockలో లేదు.", "source": "CATALOG"}
            return self._escalate("stock", "ఈ product ప్రస్తుతం stockలో ఉందా?", product)

        if self._contains(text, self.DELIVERY_WORDS):
            if product.get("delivery_available"):
                return {"status": "ANSWERED", "answer": "Seller delivery available అని confirm చేశారు.", "source": "CATALOG"}
            return self._escalate("delivery", "ఈ productకి delivery availableనా?", product)

        if self._contains(text, self.VIDEO_WORDS):
            media_id = str(product.get("video_media_id") or "").strip()
            if media_id:
                return {"status": "VIDEO_AVAILABLE", "video_media_id": media_id, "answer": "Seller product video available ఉంది."}
            return {"status": "NO_VIDEO", "answer": "ఈ productకి seller video ఇంకా add చేయలేదు."}

        if self._contains(text, self.FEATURES_WORDS):
            features = product.get("features") or []
            if features:
                return {"status": "ANSWERED", "answer": "\n".join(f"• {item}" for item in features), "source": "CATALOG"}

        normalized_key = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE).strip()
        if normalized_key:
            saved = self.catalog.get_faq(product_id, normalized_key)
            if saved:
                return {"status": "ANSWERED", "answer": saved, "source": "SELLER_FAQ"}
        return self._escalate(normalized_key or "general", question, product)

    def save_seller_answer(self, product_id: int, question: str, answer: str) -> None:
        key = re.sub(r"[^\w\s]", "", str(question or "").casefold(), flags=re.UNICODE).strip()
        self.catalog.save_faq(product_id, key or question, answer, source="SELLER_CONFIRMED")

    @staticmethod
    def _contains(text: str, words) -> bool:
        return any(word in text for word in words)

    @staticmethod
    def _money(value: Any) -> str:
        number = float(value)
        return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"

    @staticmethod
    def _escalate(key: str, question: str, product: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ASK_SELLER_ONCE",
            "question_key": str(key),
            "seller_question": str(question).strip(),
            "product_id": int(product["id"]),
            "seller_user_id": str(product["seller_user_id"]),
            "answer": "ఈ detail seller నుంచి confirm కావాలి. PODX sellerని ఒక్కసారి అడుగుతుంది.",
        }
