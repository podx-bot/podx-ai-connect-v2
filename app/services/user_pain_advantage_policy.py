"""PODX user-pain prevention contracts.

This registry converts recurring marketplace friction into explicit product guarantees
that can be validated in CI. It is intentionally domain-agnostic at the interface so
new verticals can inherit the same prevention model instead of adding one-off patches.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PainPreventionRule:
    key: str
    pain: str
    podx_advantage: str
    required_behaviours: tuple[str, ...]


class UserPainAdvantagePolicy:
    """Reference-app friction -> PODX advantage contract by domain."""

    GLOBAL_RULES = (
        PainPreventionRule(
            "duplicate_questions",
            "User is repeatedly asked for details PODX already knows.",
            "Reuse confirmed profile and conversation facts; ask only genuinely missing or conflicting facts.",
            ("PROFILE_REUSE", "STATE_MERGE", "MISSING_ONLY_CLARIFICATION"),
        ),
        PainPreventionRule(
            "wrong_role_routing",
            "A multi-role user is forced into the wrong permanent role or old flow.",
            "Resolve role from the active request and message context, not only the stored profile label.",
            ("CONTEXTUAL_ROLE", "STATE_FIRST_ROUTING", "DOMAIN_SWITCH"),
        ),
        PainPreventionRule(
            "bot_dead_end",
            "The automated flow cannot solve the request and keeps looping.",
            "Maximise auto-resolution, then route to the counterpart, direct contact, or human/admin support.",
            ("AUTO_RESOLVE", "COUNTERPART_RELAY", "HUMAN_ESCALATION"),
        ),
        PainPreventionRule(
            "status_black_box",
            "The user cannot tell what is happening after submitting a request.",
            "Expose simple progress: active, matched, contacted, responded, waiting, confirmed, or escalated.",
            ("VISIBLE_STATUS", "OBSERVABILITY", "NO_SILENT_DROP"),
        ),
    )

    DOMAIN_RULES = {
        "PROFILE": (
            PainPreventionRule(
                "onboarding_fatigue",
                "Long registration blocks the user before value is delivered.",
                "Collect the minimum profile first and progressively enrich only when required.",
                ("MINIMUM_PROFILE", "PROGRESSIVE_PROFILE", "VOICE_TEXT_PARITY"),
            ),
        ),
        "JOBS": (
            PainPreventionRule(
                "irrelevant_job_match",
                "Seeker receives weak or irrelevant jobs/workers.",
                "Rank using skill/subject, location, availability, pay and constraints before notifying.",
                ("RELEVANCE_RANKING", "LOCATION_MATCH", "CONSTRAINT_MATCH"),
            ),
            PainPreventionRule(
                "job_no_response_blackhole",
                "Application/request is sent but the seeker never knows what happened.",
                "Keep the request active, track employer response and widen targeting when needed.",
                ("ACTIVE_HOLD", "TARGET_WIDENING", "VISIBLE_STATUS"),
            ),
        ),
        "COMMERCE": (
            PainPreventionRule(
                "seller_no_response",
                "Buyer asks a product question and the conversation stalls.",
                "Relay the exact doubt, preserve pending state, and escalate if the seller does not resolve it.",
                ("DOUBT_RELAY", "PENDING_STATE", "ESCALATE_NO_RESPONSE"),
            ),
            PainPreventionRule(
                "delivery_expectation_gap",
                "Buyer and seller assume different delivery/availability terms.",
                "Confirm availability and fulfilment terms before final confirmation.",
                ("AVAILABILITY_CONFIRM", "DELIVERY_CONFIRM", "FINAL_SUMMARY"),
            ),
        ),
        "SERVICES": (
            PainPreventionRule(
                "service_scope_mismatch",
                "Customer and provider disagree about what the job includes.",
                "Capture problem, scope, price basis and timing before booking confirmation.",
                ("SCOPE_CONFIRM", "PRICE_BASIS", "TIME_CONFIRM"),
            ),
        ),
        "MOBILITY": (
            PainPreventionRule(
                "hidden_ride_price_change",
                "Passenger sees an unexpected fare or cost-sharing change.",
                "Show fare basis before confirmation and require explicit re-confirmation after material changes.",
                ("FARE_BASIS", "CHANGE_DETECTION", "RECONFIRM"),
            ),
            PainPreventionRule(
                "ride_safety_uncertainty",
                "Passenger/driver lacks confidence in counterpart or vehicle status.",
                "Use identity/vehicle verification context, consent, and safe contact exchange.",
                ("KYC_CONTEXT", "CONSENT", "SAFE_CONTACT_EXCHANGE"),
            ),
        ),
        "FREELANCE": (
            PainPreventionRule(
                "project_scope_ambiguity",
                "Client and freelancer interpret deliverables differently.",
                "Confirm deliverables, budget, deadline and revision expectations before hire.",
                ("DELIVERABLES", "BUDGET_CONFIRM", "DEADLINE_CONFIRM"),
            ),
        ),
        "RFQ": (
            PainPreventionRule(
                "quote_apples_oranges",
                "Quotes cannot be compared because suppliers answered different scopes.",
                "Normalise requested specification and compare quotes on the same basis.",
                ("NORMALIZED_SCOPE", "QUOTE_COMPARISON", "CONFLICT_CLARIFICATION"),
            ),
        ),
        "SUPPORT": (
            PainPreventionRule(
                "support_loop_without_resolution",
                "User repeats the same problem to automation without progress.",
                "Track attempts and escalate with context instead of restarting the conversation.",
                ("ATTEMPT_LIMIT", "CONTEXT_PRESERVATION", "HUMAN_ESCALATION"),
            ),
        ),
    }

    @classmethod
    def rules_for(cls, domain: str) -> tuple[PainPreventionRule, ...]:
        key = str(domain or "").upper()
        return cls.GLOBAL_RULES + cls.DOMAIN_RULES.get(key, ())

    @classmethod
    def rule_keys(cls, domain: str) -> set[str]:
        return {rule.key for rule in cls.rules_for(domain)}

    @classmethod
    def required_behaviours(cls, domain: str) -> set[str]:
        behaviours: set[str] = set()
        for rule in cls.rules_for(domain):
            behaviours.update(rule.required_behaviours)
        return behaviours

    @classmethod
    def validate_domains(cls, domains: tuple[str, ...]) -> dict[str, list[str]]:
        """Return missing contract problems; empty dict means the matrix is complete."""
        issues: dict[str, list[str]] = {}
        for domain in domains:
            rules = cls.rules_for(domain)
            problems: list[str] = []
            if len(rules) <= len(cls.GLOBAL_RULES):
                problems.append("missing_domain_specific_rule")
            for rule in rules:
                if not rule.key or not rule.pain or not rule.podx_advantage:
                    problems.append(f"incomplete_rule:{rule.key or 'unknown'}")
                if not rule.required_behaviours:
                    problems.append(f"missing_behaviours:{rule.key}")
            if problems:
                issues[str(domain).upper()] = problems
        return issues
