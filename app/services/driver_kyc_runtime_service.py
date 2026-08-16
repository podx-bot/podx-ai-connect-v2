from __future__ import annotations

import os
import re


class DriverKYCRuntimeService:
    def __init__(self, repository, user_repository=None, admin_mobile: str | None = None) -> None:
        self.repository = repository
        self.users = user_repository
        self.admin_mobile = str(admin_mobile or os.getenv("PODX_ADMIN_MOBILE") or "").strip()

    def process(self, sender_user_id: str, message: str) -> str | None:
        clean = " ".join(str(message or "").strip().split())
        if not clean:
            return None
        if re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+START", clean):
            self.repository.start(sender_user_id)
            return self._status_text(sender_user_id, prefix="✅ Driver KYC started.\n")
        if re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+STATUS", clean):
            return self._status_text(sender_user_id)
        if re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+SUBMIT", clean):
            result = self.repository.submit(sender_user_id)
            if result.get("result") == "MISSING":
                return "KYC submit చేయడానికి ఇంకా కావాలి: " + ", ".join(result.get("missing") or [])
            return "✅ Driver KYC reviewకి submit అయింది."

        m = re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+DL\s+(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)", clean)
        if m:
            self.repository.save_document(sender_user_id, "DL", document_number=m.group(1).strip(), expiry_date=m.group(2), media_ref=m.group(3).strip())
            return "✅ Driving licence saved."
        m = re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+VEHICLE\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)", clean)
        if m:
            self.repository.save_document(sender_user_id, "VEHICLE", document_number=m.group(1).strip(), vehicle_details=m.group(2).strip(), media_ref=m.group(3).strip())
            return "✅ Vehicle details saved."
        m = re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+INSURANCE\s+(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)", clean)
        if m:
            self.repository.save_document(sender_user_id, "INSURANCE", document_number=m.group(1).strip(), expiry_date=m.group(2), media_ref=m.group(3).strip())
            return "✅ Insurance details saved."
        m = re.fullmatch(r"(?i)(?:DRIVER\s+)?KYC\s+PHOTO\s+(.+)", clean)
        if m:
            self.repository.save_document(sender_user_id, "VEHICLE_PHOTO", media_ref=m.group(1).strip())
            return "✅ Vehicle photo saved."

        approve = re.fullmatch(r"(?i)KYC\s+APPROVE\s+(\S+)", clean)
        if approve:
            if not self._is_admin(sender_user_id):
                return "ఈ KYC review command admin/internal useకి మాత్రమే."
            result = self.repository.review_profile(approve.group(1), sender_user_id, True)
            return "Driver KYC దొరకలేదు." if result.get("result") == "NOT_FOUND" else f"✅ Driver {approve.group(1)} KYC approved."
        reject = re.fullmatch(r"(?i)KYC\s+REJECT\s+(\S+)\s*\|\s*(.+)", clean)
        if reject:
            if not self._is_admin(sender_user_id):
                return "ఈ KYC review command admin/internal useకి మాత్రమే."
            result = self.repository.review_profile(reject.group(1), sender_user_id, False, reject.group(2).strip())
            return "Driver KYC దొరకలేదు." if result.get("result") == "NOT_FOUND" else f"❌ Driver {reject.group(1)} KYC rejected. Reason: {reject.group(2).strip()}"
        return None

    def _is_admin(self, sender_user_id: str) -> bool:
        return bool(self.admin_mobile and str(sender_user_id) == self.admin_mobile)

    def _status_text(self, driver_user_id: str, prefix: str = "") -> str:
        state = self.repository.status(driver_user_id)
        status = state.get("status") or "NOT_STARTED"
        missing = state.get("missing") or []
        expired = state.get("expired") or []
        lines = [f"KYC status: {status}"]
        if missing:
            lines.append("Pending: " + ", ".join(missing))
        if expired:
            lines.append("Expired: " + ", ".join(expired))
        if state.get("eligible"):
            lines.append("✅ Driver verification active")
        elif status == "APPROVED" and expired:
            lines.append("⚠️ Verification renewal required")
        return prefix + "\n".join(lines)


class DriverKYCAwareConversationService:
    def __init__(self, kyc_runtime, delegate) -> None:
        self.kyc_runtime = kyc_runtime
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def handle_text_message(self, sender_mobile: str, message_text: str):
        reply = self.kyc_runtime.process(sender_mobile, message_text)
        if reply is not None:
            return reply
        return self.delegate.handle_text_message(sender_mobile, message_text)

    def process(self, sender_mobile: str, message_text: str):
        reply = self.kyc_runtime.process(sender_mobile, message_text)
        if reply is not None:
            return reply
        if hasattr(self.delegate, "process"):
            return self.delegate.process(sender_mobile, message_text)
        return None
