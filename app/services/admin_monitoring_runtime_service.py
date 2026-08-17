"""WhatsApp admin commands for operational visibility."""
from __future__ import annotations

import os
import re


class AdminMonitoringRuntimeService:
    def __init__(self, monitoring, delegate, admin_mobile: str | None = None) -> None:
        self.monitoring = monitoring
        self.delegate = delegate
        self.admin_mobile = str(admin_mobile or os.getenv("PODX_ADMIN_MOBILE") or "").strip()

    def process(
        self,
        sender_user_id: str | None = None,
        message: str = "",
        *,
        sender_mobile: str | None = None,
    ) -> str:
        """Process admin commands while remaining compatible with webhook callers.

        Older wrappers call ``process(sender_user_id, message)`` positionally while
        the WhatsApp webhook calls ``process(sender_mobile=..., message=...)``.
        Accept both names so this outermost wrapper cannot break ordinary traffic.
        """
        sender = str(sender_mobile if sender_mobile is not None else (sender_user_id or ""))
        clean = " ".join(str(message or "").strip().split())
        if not clean.upper().startswith("ADMIN "):
            return self.delegate.process(sender, message)
        if not self.admin_mobile or sender != self.admin_mobile:
            return "ఈ admin command authorized కాదు."

        upper = clean.upper()
        if upper in {"ADMIN STATUS", "ADMIN DASHBOARD", "ADMIN HEALTH"}:
            s = self.monitoring.snapshot()
            return (
                "🛠️ PODX Admin Status\n"
                f"Unresolved: {s['unresolved']}\nRuntime errors: {s['runtime_errors']}\n"
                f"Failed deliveries: {s['failed_deliveries']}\nKYC submitted: {s['kyc_submitted']}\n"
                f"KYC rejected: {s['kyc_rejected']}\nOpen RFQs: {s['open_rfqs']}\n"
                f"Open rides: {s['open_rides']}\nAccepted ride bookings: {s['accepted_ride_bookings']}"
            )
        m = re.fullmatch(r"(?i)ADMIN\s+(UNRESOLVED|ERRORS)(?:\s+(\d+))?", clean)
        if m:
            rows = self.monitoring.unresolved(int(m.group(2) or 10))
            if not rows:
                return "✅ Unresolved/runtime error queue empty."
            lines = ["⚠️ PODX unresolved/errors:"]
            for row in rows:
                lines.append(f"#{row['id']} {row['outcome']} • {row['detected_domain']} • {row['message_preview'] or '-'}")
            return "\n".join(lines)
        m = re.fullmatch(r"(?i)ADMIN\s+KYC(?:\s+(\d+))?", clean)
        if m:
            rows = self.monitoring.pending_kyc(int(m.group(1) or 10))
            if not rows:
                return "✅ KYC review queue empty."
            return "\n".join(["🪪 KYC review queue:"] + [f"{x['driver_user_id']} • {x['status']}" for x in rows])
        m = re.fullmatch(r"(?i)ADMIN\s+DELIVERIES(?:\s+(\d+))?", clean)
        if m:
            rows = self.monitoring.failed_deliveries(int(m.group(1) or 10))
            if not rows:
                return "✅ Failed delivery queue empty."
            return "\n".join(["📨 Failed deliveries:"] + [f"{x.get('recipient_mobile') or '-'} • {x.get('status')} • {x.get('error_message') or '-'}" for x in rows])
        m = re.fullmatch(r"(?i)ADMIN\s+RFQS(?:\s+(\d+))?", clean)
        if m:
            rows = self.monitoring.open_rfqs(int(m.group(1) or 10))
            if not rows:
                return "✅ Open RFQ queue empty."
            return "\n".join(["📋 Open RFQs:"] + [f"#{x['id']} {x['rfq_type']} • {x.get('title') or '-'}" for x in rows])
        return "Admin commands: ADMIN STATUS | ADMIN UNRESOLVED | ADMIN KYC | ADMIN DELIVERIES | ADMIN RFQS"
