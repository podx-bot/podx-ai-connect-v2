"""Shareable business desk: customer asks PODX, owner teaches once, future answers reuse RAG."""
from __future__ import annotations

import re
from typing import Optional


class BusinessCustomerDeskService:
    def __init__(self, repository, rag_repository, whatsapp_service, user_repository=None) -> None:
        self.repository = repository
        self.rag = rag_repository
        self.whatsapp = whatsapp_service
        self.users = user_repository

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None

        setup = re.fullmatch(r"BUSINESS\s+ON\s+([^|]+?)(?:\s*\|\s*(.+))?", clean, re.IGNORECASE)
        if setup:
            if not self._registered(sender_mobile):
                return "ముందుగా PODX registration complete చేయండి."
            desk = self.repository.enable(sender_mobile, setup.group(1).strip(), setup.group(2))
            return (
                f"✅ PODX Business Desk ON\n"
                f"Business: {desk['business_name']}\n"
                f"Code: {desk['business_code']}\n\n"
                f"Customersకి ఇలా చెప్పండి: `ASK {desk['business_code']} <question>`\n"
                "తెలియని question వస్తే PODX మిమ్మల్ని ఒక్కసారి అడిగి answer నేర్చుకుంటుంది."
            )

        if re.fullmatch(r"BUSINESS\s+OFF", clean, re.IGNORECASE):
            if self.repository.disable(sender_mobile):
                return "✅ PODX Business Desk OFF చేశాం."
            return "Business Desk ఇంకా setup కాలేదు."

        if re.fullmatch(r"BUSINESS\s+STATUS", clean, re.IGNORECASE):
            desk = self.repository.find_by_owner(sender_mobile)
            if not desk:
                return "Business Desk ఇంకా setup కాలేదు."
            return f"Business: {desk['business_name']}\nCode: {desk['business_code']}\nStatus: {desk['status']}"

        owner_answer = re.fullmatch(r"BIZ\s+ANSWER\s+#?(\d+)\s*\|\s*(.+)", clean, re.IGNORECASE)
        if owner_answer:
            return self._owner_answer(sender_mobile, int(owner_answer.group(1)), owner_answer.group(2).strip())

        natural_answer = re.fullmatch(r"BIZ\s+ANSWER\s+(.+)", clean, re.IGNORECASE)
        if natural_answer:
            pending = self.repository.latest_pending_for_owner(sender_mobile)
            if not pending:
                return "Pending business question లేదు."
            return self._owner_answer(sender_mobile, int(pending["id"]), natural_answer.group(1).strip())

        ask = re.fullmatch(r"(?:ASK|PODX)\s+([A-Z0-9]{4,20})\s+(.+)", clean, re.IGNORECASE)
        if ask:
            return self._customer_ask(sender_mobile, ask.group(1), ask.group(2).strip())
        return None

    def _customer_ask(self, customer_mobile: str, code: str, question: str) -> str:
        desk = self.repository.find_by_code(code)
        if not desk:
            return "❌ ఈ PODX Business Code activeగా లేదు."
        if str(desk["owner_mobile"]) == str(customer_mobile):
            return "ఇది మీ Business Desk code. Customer questionని వేరే WhatsApp user నుంచి అడగండి."

        answer = self._rag_answer(desk, question)
        if answer:
            return f"🏪 {desk['business_name']}\n\n{answer}\n\n✅ Owner-confirmed PODX answer"

        ticket, created = self.repository.create_or_get_pending(desk, customer_mobile, question)
        if created:
            owner_message = (
                f"🤖 PODX Customer Desk — Question #{ticket['id']}\n\n"
                f"Business: {desk['business_name']}\n"
                f"Customer asks: {question}\n\n"
                f"Reply: BIZ ANSWER {ticket['id']} | <your answer>\n"
                "ఈ answer save అయి futureలో same/similar questionకి PODX auto-answer చేస్తుంది."
            )
            self._send(str(desk["owner_mobile"]), owner_message)
            return f"🏪 {desk['business_name']} owner-confirmed answer ఇంకా లేదు. Ownerని ఒక్కసారి అడిగాను; reply వచ్చిన వెంటనే మీకు పంపిస్తాను."
        return f"⏳ {desk['business_name']}కి ఇదే question ఇప్పటికే పంపాం. Owner answer వచ్చిన వెంటనే మీకు పంపిస్తాను."

    def _owner_answer(self, owner_mobile: str, question_id: int, answer: str) -> str:
        if not answer:
            return "Answer ఖాళీగా ఉండకూడదు."
        pending = self.repository.pending_for_owner(owner_mobile, question_id)
        if not pending:
            return "❌ ఈ pending question మీ Business Deskకి చెందినది కాదు లేదా ఇప్పటికే answered అయింది."
        resolved = self.repository.answer(owner_mobile, question_id, answer)
        if not resolved:
            return "Question answer save చేయలేకపోయాం."
        desk = self.repository.find_by_code(str(resolved["business_code"])) or {}
        subject = str(desk.get("business_name") or resolved["business_code"])
        self.rag.add(
            "BUSINESS_FAQ",
            f"Question: {resolved['question']} Answer: {answer}",
            owner_user_id=str(owner_mobile),
            subject=subject,
            source_type="SELLER_CONFIRMED",
            source_ref=f"business-question:{question_id}",
            metadata={"question": resolved["question"], "answer": answer, "business_code": resolved["business_code"]},
        )
        self._send(
            str(resolved["customer_mobile"]),
            f"🏪 {subject}\n\n{answer}\n\n✅ Business owner confirmed",
        )
        return f"✅ Answer #{question_id} customerకి పంపాం మరియు PODX Business Desk knowledgeలో save చేశాం."

    def _rag_answer(self, desk: dict, question: str) -> str | None:
        rows = self.rag.retrieve(
            question,
            namespaces=["BUSINESS_FAQ"],
            owner_user_id=str(desk["owner_mobile"]),
            subject=str(desk["business_name"]),
            limit=3,
        )
        for row in rows:
            if float(row.get("retrieval_score") or 0) < 0.65:
                continue
            metadata = row.get("metadata") or {}
            answer = str(metadata.get("answer") or "").strip()
            if answer:
                return answer
        return None

    def _registered(self, mobile: str) -> bool:
        if self.users is None:
            return True
        user = self.users.find_by_whatsapp_mobile(str(mobile)) or {}
        return int(user.get("registration_complete") or 0) == 1

    def _send(self, recipient: str, message: str) -> None:
        try:
            self.whatsapp.send_text_message(recipient_mobile=recipient, message=message)
        except Exception:
            pass
