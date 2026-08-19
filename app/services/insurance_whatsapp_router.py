from app.services.insurance_assistant_service import InsuranceAssistantService


class InsuranceWhatsAppRouter:
    """Small adapter used by WhatsApp text/voice flows.

    Keeps insurance routing isolated from the broader conversation service and
    only claims messages that clearly look insurance-related.
    """

    INSURANCE_MARKERS = (
        "insurance",
        "policy",
        "insurer",
        "premium",
        "coverage",
        "claim",
        "cashless",
        "waiting period",
        "nominee",
        "ఇన్సూరెన్స్",
        "పాలసీ",
        "ప్రీమియం",
        "కవరేజ్",
        "క్లెయిమ్",
        "క్యాష్‌లెస్",
        "వెయిటింగ్ పీరియడ్",
        "నామినీ",
    )

    def __init__(self, assistant: InsuranceAssistantService | None = None):
        self.assistant = assistant or InsuranceAssistantService()

    def process_text(self, message: str) -> str | None:
        text = str(message or "").strip().lower()
        if not text or not any(marker in text for marker in self.INSURANCE_MARKERS):
            return None
        result = self.assistant.answer(message)
        answer = str(result.get("answer") or "").strip()
        return answer or None
