"""Ask seller once, learn the answer, and reuse it for future buyer questions."""
from __future__ import annotations


class SellerAIEscalationService:
    def __init__(self, repository, product_desk, whatsapp_service, contact_resolver) -> None:
        self.repository = repository
        self.product_desk = product_desk
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver

    def escalate(self, buyer_user_id: str, desk_result: dict, subject: str) -> dict:
        record = self.repository.create_once(
            product_id=int(desk_result["product_id"]),
            seller_user_id=str(desk_result["seller_user_id"]),
            buyer_user_id=str(buyer_user_id),
            question_key=str(desk_result.get("question_key") or "general"),
            question=str(desk_result.get("seller_question") or "").strip(),
        )
        if record.get("created"):
            seller = self.contact_resolver(record["seller_user_id"]) or {}
            mobile = str(seller.get("mobile") or seller.get("phone") or record["seller_user_id"])
            self.whatsapp.send_text_message(
                mobile,
                "🤖 PODX AI Deskకి ఒక buyer question వచ్చింది.\n"
                f"Product: {subject}\n"
                f"Question: {record['question']}\n\n"
                "ఈ messageకి answer మాత్రమే reply చేయండి. PODX దాన్ని save చేసి futureలో ఇదే doubtకి automaticగా answer చేస్తుంది.",
            )
        return record

    def consume_seller_reply(self, sender_user_id: str, message: str) -> str | None:
        pending = self.repository.latest_pending_for_seller(str(sender_user_id))
        if not pending:
            return None
        answer = str(message or "").strip()
        if not answer:
            return None
        saved = self.repository.answer(int(pending["id"]), answer)
        if not saved:
            return None
        self.product_desk.save_seller_answer(int(saved["product_id"]), str(saved["question_key"]), answer)
        buyer = self.contact_resolver(saved["buyer_user_id"]) or {}
        buyer_mobile = str(buyer.get("mobile") or buyer.get("phone") or saved["buyer_user_id"])
        self.whatsapp.send_text_message(
            buyer_mobile,
            f"✅ Seller confirm చేశారు:\n{answer}",
        )
        return "✅ Thanks. PODX ఈ answerని save చేసింది. ఇక ఇదే question మళ్లీ వస్తే AI automaticగా answer చేస్తుంది."
