"""User controls for optional discovery/proactive notifications."""
from __future__ import annotations

import re
from typing import Optional


class ProactiveAlertPreferenceService:
    OFF_PHRASES = {
        "alerts off", "alert off", "notifications off", "notification off",
        "అలర్ట్స్ ఆఫ్", "నోటిఫికేషన్స్ ఆఫ్", "ప్రొమో అలర్ట్స్ వద్దు",
    }
    ON_PHRASES = {
        "alerts on", "alert on", "notifications on", "notification on",
        "అలర్ట్స్ ఆన్", "నోటిఫికేషన్స్ ఆన్",
    }
    STATUS_PHRASES = {
        "alerts status", "alert status", "notifications status", "notification status",
        "అలర్ట్స్ స్టేటస్", "నోటిఫికేషన్స్ స్టేటస్",
    }

    def __init__(self, repository) -> None:
        self.repository = repository

    def process(self, sender_mobile: str, message: str) -> Optional[str]:
        clean = " ".join(str(message or "").casefold().strip().split())
        clean = re.sub(r"[.!?]+$", "", clean).strip()
        if clean in self.OFF_PHRASES:
            self.repository.set_enabled(sender_mobile, False)
            return (
                "🔕 Optional PODX discovery alerts OFF చేశాను.\n"
                "Product availability, local-demand, nearby-vendor alerts pause అవుతాయి.\n"
                "✅ Orders, bookings, jobs, RFQs, confirmations మాత్రం ఎప్పటిలాగే వస్తాయి."
            )
        if clean in self.ON_PHRASES:
            self.repository.set_enabled(sender_mobile, True)
            return (
                "🔔 Optional PODX discovery alerts ON చేశాను.\n"
                "Relevant local product/demand/vendor opportunities మళ్లీ రావచ్చు."
            )
        if clean in self.STATUS_PHRASES:
            enabled = self.repository.is_enabled(sender_mobile)
            state = "ON 🔔" if enabled else "OFF 🔕"
            return (
                f"Optional discovery alerts: {state}\n"
                "Transactional alerts (orders/bookings/jobs/RFQs/confirmations): ALWAYS ON ✅"
            )
        return None
