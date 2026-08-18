"""Domain-specific PODX runtime quality guards.

These guards bind UserPainAdvantagePolicy contracts to live conversation responses
without taking ownership of the underlying business state machines. They intervene
only on strong completion/commitment signals where missing terms would otherwise
create the recurring complaint patterns captured in the policy registry.
"""
from __future__ import annotations

from app.services.user_pain_advantage_policy import UserPainAdvantagePolicy


class DomainComplaintPreventionService:
    def __init__(self, delegate, category_brain=None, observability_repository=None) -> None:
        self.delegate = delegate
        self.category_brain = category_brain
        self.observability = observability_repository

    def process(self, sender_mobile: str, message: str) -> str:
        sender = str(sender_mobile)
        clean = str(message or "").strip()
        decision = self._decision(clean)
        domain = decision[0]

        try:
            reply = self.delegate.process(sender_mobile=sender, message=clean)
        except TypeError:
            reply = self.delegate.process(sender, clean)

        text = str(reply or "").strip()
        if not text:
            return text

        guarded, outcome = self._guard(domain, text)
        if outcome:
            self._record(sender, clean, domain, outcome)
        return guarded

    def _decision(self, message: str) -> tuple[str, str, str]:
        if self.category_brain is None:
            return ("GENERAL", "UNKNOWN", "UNKNOWN")
        try:
            result = self.category_brain.classify(message)
            return (
                str(getattr(result, "category", "GENERAL") or "GENERAL").upper(),
                str(getattr(result, "side", "UNKNOWN") or "UNKNOWN").upper(),
                str(getattr(result, "action", "UNKNOWN") or "UNKNOWN").upper(),
            )
        except Exception:
            return ("GENERAL", "UNKNOWN", "UNKNOWN")

    def _guard(self, domain: str, text: str) -> tuple[str, str | None]:
        lower = text.casefold()

        if domain == "JOBS" and self._has_any(lower, (
            "application sent", "applied", "request sent", "అప్లై", "పంపించాం", "పంపబడింది"
        )) and not self._has_any(lower, (
            "status", "active", "waiting", "matched", "responded", "స్టేటస్", "వెయిటింగ్"
        )):
            return text + "\n\nStatus: ACTIVE — employer response కోసం track చేస్తాను; reply రాకపోతే targeting widen చేయాలి.", "JOB_STATUS_ADDED"

        if domain == "COMMERCE" and self._looks_final(lower):
            missing = []
            if not self._has_any(lower, ("available", "availability", "stock", "అందుబాటులో", "స్టాక్")):
                missing.append("availability")
            if not self._has_any(lower, ("delivery", "pickup", "డెలివరీ", "పికప్")):
                missing.append("delivery/pickup")
            if missing:
                return text + "\n\nFinal confirm ముందు " + " + ".join(missing) + " terms confirm చేయాలి.", "COMMERCE_FULFILMENT_GUARD"

        if domain == "SERVICES" and self._looks_final(lower):
            missing = []
            if not self._has_any(lower, ("scope", "problem", "issue", "work", "పని", "స్కోప్")):
                missing.append("scope")
            if not self._has_any(lower, ("price", "rate", "estimate", "₹", "ధర", "రేట్")):
                missing.append("price basis")
            if not self._has_any(lower, ("time", "today", "tomorrow", "slot", "సమయం", "ఈరోజు", "రేపు")):
                missing.append("time")
            if missing:
                return text + "\n\nBooking final చేసే ముందు " + " + ".join(missing) + " confirm చేయాలి.", "SERVICE_SCOPE_GUARD"

        if domain == "MOBILITY" and self._has_any(lower, (
            "fare changed", "updated fare", "new fare", "fare updated", "కొత్త fare", "fare మారింది", "rate మారింది"
        )) and not self._has_any(lower, ("reconfirm", "accept", "confirm", "అంగీకర", "కన్ఫర్మ్")):
            return text + "\n\nFare మారింది. కొత్త amountను accept చేస్తున్నారా? Re-confirm అవసరం.", "MOBILITY_FARE_RECONFIRM_GUARD"

        if domain == "FREELANCE" and self._looks_final(lower):
            missing = []
            if not self._has_any(lower, ("deliverable", "scope", "logo", "website", "design", "డెలివరబుల్")):
                missing.append("deliverables")
            if not self._has_any(lower, ("budget", "price", "₹", "బడ్జెట్")):
                missing.append("budget")
            if not self._has_any(lower, ("deadline", "date", "days", "time", "డెడ్‌లైన్")):
                missing.append("deadline")
            if missing:
                return text + "\n\nHire final చేసే ముందు " + " + ".join(missing) + " confirm చేయాలి.", "FREELANCE_SCOPE_GUARD"

        if domain == "B2B_RFQ" and self._has_any(lower, (
            "compare quotes", "quote comparison", "best quote", "quotes", "కోట్స్", "కోటేషన్"
        )) and not self._has_any(lower, (
            "same specification", "same basis", "normalized", "normalised", "ఒకే specification", "ఒకే basis"
        )):
            return text + "\n\nQuotesను same specification / quantity / delivery basisలో normalize చేసి compare చేయాలి.", "RFQ_NORMALIZATION_GUARD"

        if domain == "SUPPORT" and self._has_any(lower, (
            "unable", "cannot resolve", "not resolved", "unresolved", "పరిష్కారం కాలేదు", "సాల్వ్ కాలేదు"
        )) and not self._has_any(lower, ("human", "admin", "contact", "escalat", "support team")):
            return text + "\n\nఈ issueను contextతో human/admin supportకి escalate చేయాలి; conversation restart చేయను.", "SUPPORT_ESCALATION_GUARD"

        return text, None

    @staticmethod
    def _looks_final(value: str) -> bool:
        return DomainComplaintPreventionService._has_any(value, (
            "final confirm", "final confirmation", "confirmed", "booking confirmed", "order confirmed",
            "final summary", "confirm order", "hire confirmed", "కన్ఫర్మ్", "ఫైనల్"
        ))

    @staticmethod
    def _has_any(value: str, markers: tuple[str, ...]) -> bool:
        return any(marker in value for marker in markers)

    def _record(self, sender: str, message: str, domain: str, outcome: str) -> None:
        if self.observability is None:
            return
        try:
            self.observability.record(
                sender,
                message,
                domain,
                outcome,
                route_source="domain_quality_guard",
                metadata={"policy_rules": sorted(UserPainAdvantagePolicy.rule_keys(domain))},
            )
        except Exception:
            return
