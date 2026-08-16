from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecoveryNotice:
    kind: str
    message: str


class WebhookRecoveryService:
    """Best-effort user recovery notices for partially processed webhook events.

    Recovery replies are deliberately non-transactional: they never undo a
    persisted inbound event or a completed business action. Their only job is
    to prevent silent failures and tell the user how to safely continue.
    """

    NOTICES = {
        "audio": RecoveryNotice(
            "audio",
            "🎙️ Voice process పూర్తికాలేదు. దయచేసి చిన్న voice note మళ్లీ పంపండి లేదా textలో పంపండి.",
        ),
        "image": RecoveryNotice(
            "image",
            "📷 Photo process పూర్తికాలేదు. దయచేసి photo మళ్లీ పంపండి లేదా వివరాలు textలో పంపండి.",
        ),
        "document": RecoveryNotice(
            "document",
            "📄 Document process పూర్తికాలేదు. దయచేసి file మళ్లీ పంపండి లేదా details textలో పంపండి.",
        ),
        "location": RecoveryNotice(
            "location",
            "📍 Location process పూర్తికాలేదు. దయచేసి location మళ్లీ share చేయండి. మీ previous details safeగా ఉన్నాయి.",
        ),
        "text": RecoveryNotice(
            "text",
            "⚠️ మీ message processలో temporary problem వచ్చింది. దయచేసి అదే message మళ్లీ పంపండి.",
        ),
    }

    @classmethod
    def message_for(cls, kind: str) -> str:
        notice = cls.NOTICES.get(str(kind).strip().lower()) or cls.NOTICES["text"]
        return notice.message

    @classmethod
    def send(cls, whatsapp_service: Any, recipient_mobile: str, kind: str) -> dict[str, Any]:
        try:
            result = whatsapp_service.send_text_message(
                recipient_mobile=str(recipient_mobile),
                message=cls.message_for(kind),
            )
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as error:
            return {
                "success": False,
                "status": "RECOVERY_SEND_EXCEPTION",
                "error": f"{type(error).__name__}: {error}",
            }
