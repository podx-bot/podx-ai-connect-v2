from __future__ import annotations

import hashlib

from app.repositories.face_welcome_repository import FaceWelcomeRepository


class FaceWelcomeEnrollmentService:
    """Consent-first Face Welcome enrollment contract.

    V1 intentionally does not perform biometric recognition. It controls when a
    face photo may be requested/accepted and stores only a digest in PODX. This
    keeps normal Universal Profile registration photo-free while making Face
    Welcome an explicit opt-in feature.
    """

    ENABLE_PHRASES = {
        "face welcome", "enable face welcome", "face recognition welcome",
        "ఫేస్ వెల్కమ్", "ఫేస్ రికగ్నిషన్ వెల్కమ్", "face welcome enable చేయండి",
    }
    ACCEPT_PHRASES = {
        "yes", "ok", "accept", "i agree", "అవును", "సరే", "ఒప్పుకుంటున్నాను",
    }
    DECLINE_PHRASES = {
        "no", "decline", "cancel", "వద్దు", "కాదు", "ఇప్పుడు వద్దు",
    }
    DISABLE_PHRASES = {
        "disable face welcome", "remove face welcome", "delete face photo",
        "ఫేస్ వెల్కమ్ ఆఫ్", "ఫేస్ ఫోటో తొలగించండి", "ఫేస్ వెల్కమ్ తొలగించండి",
    }

    def __init__(self, repository: FaceWelcomeRepository) -> None:
        self.repository = repository

    def process_text(self, whatsapp_mobile: str, message: str) -> str | None:
        normalized = " ".join(str(message or "").strip().lower().split())
        if not normalized:
            return None

        if normalized in self.DISABLE_PHRASES:
            self.repository.revoke(whatsapp_mobile)
            return "✅ Face Welcome off చేశాను. Saved face enrollment reference తొలగించబడింది."

        state = self.repository.get(whatsapp_mobile) or {}
        consent_status = str(state.get("consent_status") or "NOT_ASKED")

        if normalized in self.ENABLE_PHRASES:
            return self.consent_prompt()

        if consent_status != "ACCEPTED" and normalized in self.ACCEPT_PHRASES:
            self.repository.mark_consent(whatsapp_mobile, True)
            return self.photo_prompt()

        if consent_status != "ACCEPTED" and normalized in self.DECLINE_PHRASES:
            self.repository.mark_consent(whatsapp_mobile, False)
            return "సరే. Face Welcome enable చేయలేదు. మీ normal PODX profile అలాగే కొనసాగుతుంది."

        return None

    @staticmethod
    def consent_prompt() -> str:
        return (
            "🙂 Face Welcome optional feature. Shop/business వద్ద మిమ్మల్ని గుర్తించి welcome చేయడానికి "
            "మీ face photo enrollment అవసరం. ఇది normal PODX profileకి mandatory కాదు.\n\n"
            "మీరు Face Welcome కోసం photo ఉపయోగించడానికి consent ఇస్తారా?\n"
            "అవును / వద్దు"
        )

    @staticmethod
    def photo_prompt() -> str:
        return (
            "📸 ధన్యవాదాలు. ఇప్పుడు WhatsApp Attachment → Camera/Photo ద్వారా clear front-face photo పంపండి. "
            "ఒక్క face, మంచి light, blur లేకుండా ఉండాలి."
        )

    def accept_photo(self, whatsapp_mobile: str, image_bytes: bytes) -> str | None:
        state = self.repository.get(whatsapp_mobile) or {}
        if str(state.get("consent_status") or "") != "ACCEPTED":
            return None
        if not image_bytes:
            return "📸 Photo ఖాళీగా వచ్చింది. Clear face photo మళ్లీ పంపండి."

        digest = hashlib.sha256(image_bytes).hexdigest()
        self.repository.save_photo_digest(whatsapp_mobile, digest)
        return (
            "✅ Face Welcome photo enrollment save అయింది.\n"
            "Future in-store Face Welcome matching కోసం enrollment readyగా ఉంది."
        )

    def status_text(self, whatsapp_mobile: str) -> str:
        state = self.repository.get(whatsapp_mobile) or {}
        if not state:
            return "Face Welcome: Not enabled"
        consent = str(state.get("consent_status") or "NOT_ASKED")
        has_photo = bool(state.get("photo_sha256"))
        enabled = bool(int(state.get("enabled") or 0))
        if enabled and consent == "ACCEPTED" and has_photo:
            return "Face Welcome: Enabled · Photo enrolled"
        if consent == "ACCEPTED":
            return "Face Welcome: Consent accepted · Photo pending"
        return "Face Welcome: Not enabled"
