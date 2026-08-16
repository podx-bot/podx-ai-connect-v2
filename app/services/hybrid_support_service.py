"""Hybrid AI -> human support -> learned-answer loop for unresolved PODX questions."""
from __future__ import annotations

import os
import re
from typing import Optional


class HybridSupportService:
    QUESTION_HINTS = ("?", "why", "how", "what", "when", "where", "can i", "help", "ఎలా", "ఎందుకు", "ఏమిటి", "ఎప్పుడు", "ఎక్కడ", "సహాయం", "తెలియాలి", "क्या", "कैसे", "क्यों", "मदद")

    def __init__(self, repository, rag_repository, whatsapp_service, contact_resolver, admin_mobile: str | None = None) -> None:
        self.repository = repository
        self.rag = rag_repository
        self.whatsapp = whatsapp_service
        self.contact_resolver = contact_resolver
        self.admin_mobile = str(admin_mobile or os.getenv("PODX_ADMIN_MOBILE") or "").strip()

    def process(self, sender_user_id: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None
        admin_reply = self._process_admin_answer(sender_user_id, clean)
        if admin_reply is not None:
            return admin_reply
        if not self._looks_like_question(clean):
            return None

        evidence = self.rag.retrieve(clean, namespaces=["PODX_SUPPORT", "PODX_FAQ"], limit=3)
        if evidence and float(evidence[0].get("retrieval_score") or 0) >= 0.65:
            return f"🤖 {evidence[0]['content']}"

        ticket = self.repository.create_once(sender_user_id, clean)
        if ticket.get("created"):
            self._notify_admin(ticket)
            return f"🤝 ఈ ప్రశ్నకు verified answer ఇప్పుడే నా knowledgeలో లేదు. Supportకి పంపాను. Ticket #{ticket['id']}. Answer వచ్చిన తర్వాత మీకు ఇక్కడే చెప్తాను."
        return f"⏳ ఇదే ప్రశ్న Supportకి ఇప్పటికే పంపాను. Ticket #{ticket['id']} pendingలో ఉంది."

    def _process_admin_answer(self, sender_user_id: str, message: str) -> Optional[str]:
        match = re.match(r"^(?:ADMIN\s+ANSWER|SUPPORT\s+ANSWER)\s+(\d+)\s*\|\s*(.+)$", message, flags=re.I | re.S)
        if not match:
            return None
        if self.admin_mobile and self._digits(sender_user_id) != self._digits(self.admin_mobile):
            return "ఈ command PODX Support admin కోసం మాత్రమే."
        ticket_id = int(match.group(1)); answer = " ".join(match.group(2).strip().split())
        ticket = self.repository.get(ticket_id)
        if not ticket:
            return f"Support ticket #{ticket_id} దొరకలేదు."
        if str(ticket.get("status") or "").upper() != "PENDING":
            return f"Support ticket #{ticket_id} ఇప్పటికే resolve అయింది."
        knowledge_id = self.rag.add(
            "PODX_SUPPORT",
            answer,
            subject=str(ticket.get("question") or "")[:180],
            source_type="PODX_CONFIRMED",
            source_ref=f"support_ticket:{ticket_id}",
            metadata={"question": ticket.get("question"), "answered_by": str(sender_user_id)},
        )
        saved = self.repository.answer(ticket_id, answer, str(sender_user_id), knowledge_id=knowledge_id)
        if not saved:
            return f"Support ticket #{ticket_id} update కాలేదు."
        requester = self.contact_resolver(str(saved["requester_user_id"])) or {}
        mobile = str(requester.get("mobile") or requester.get("phone") or saved["requester_user_id"])
        self.whatsapp.send_text_message(
            mobile,
            f"✅ PODX Support answer (Ticket #{ticket_id}):\n{answer}\n\nఈ verified answerని PODX futureలో similar questionsకి reuse చేస్తుంది.",
        )
        return f"✅ Ticket #{ticket_id} resolve అయింది. Answer userకి పంపి PODX knowledgeలో save చేశాను."

    def _notify_admin(self, ticket: dict) -> None:
        if not self.admin_mobile:
            return
        requester = self.contact_resolver(str(ticket["requester_user_id"])) or {}
        name = str(requester.get("name") or "PODX User")
        self.whatsapp.send_text_message(
            self.admin_mobile,
            "🆘 PODX Hybrid Support\n"
            f"Ticket #{ticket['id']}\nUser: {name}\nQuestion: {ticket['question']}\n\n"
            f"Reply: ADMIN ANSWER {ticket['id']} | <verified answer>",
        )

    @classmethod
    def _looks_like_question(cls, message: str) -> bool:
        text = " ".join(str(message or "").casefold().split())
        return len(text) >= 4 and any(hint in text for hint in cls.QUESTION_HINTS)

    @staticmethod
    def _digits(value: str) -> str:
        return re.sub(r"\D", "", str(value or ""))[-15:]
