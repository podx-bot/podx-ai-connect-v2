"""Internal resilience coverage matrix for PODX production gating.

This module keeps the non-happy-path behaviours explicit so new vertical work cannot
silently drop multi-turn, multi-role, parity, recovery or escalation guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResilienceScenario:
    key: str
    concern: str
    expected_guarantees: tuple[str, ...]


class InternalResilienceMatrix:
    SCENARIOS = (
        ResilienceScenario(
            "multi_turn_state_continuity",
            "A follow-up answer must stay attached to the active request instead of restarting generic intake.",
            ("STATE_FIRST", "PENDING_CONTEXT", "NO_GENERIC_RESTART"),
        ),
        ResilienceScenario(
            "multi_role_context_switch",
            "One person can act as buyer, seller, seeker, provider, employer, worker, driver or passenger across requests.",
            ("CONTEXTUAL_ROLE", "DOMAIN_SWITCH", "NO_PERMANENT_ROLE_LOCK"),
        ),
        ResilienceScenario(
            "voice_text_parity",
            "Equivalent voice transcript and typed text must produce the same intent/category/side/action plan.",
            ("NORMALIZED_INPUT", "SAME_ROUTING_CONTRACT", "SAME_STATE_OBJECT"),
        ),
        ResilienceScenario(
            "restart_recovery",
            "After interruption or restart, confirmed business facts must be reused and only missing/conflicting facts asked again.",
            ("PERSISTED_STATE", "PROFILE_REUSE", "MISSING_ONLY_CLARIFICATION"),
        ),
        ResilienceScenario(
            "bounded_escalation",
            "Automation must not loop forever; unresolved work progresses to counterpart/contact/human support with context.",
            ("ATTEMPT_LIMIT", "CONTEXT_PRESERVATION", "HUMAN_ESCALATION"),
        ),
        ResilienceScenario(
            "no_silent_drop",
            "Every accepted request gets a visible result/status even when a lower runtime cannot answer.",
            ("VISIBLE_STATUS", "NO_SILENT_DROP", "OBSERVABILITY"),
        ),
        ResilienceScenario(
            "commitment_boundary_guard",
            "Final buy/book/hire/ride/RFQ decisions must not pass with material fulfilment terms missing.",
            ("FINAL_SUMMARY", "MATERIAL_TERM_CHECK", "RECONFIRM_ON_CHANGE"),
        ),
    )

    @classmethod
    def keys(cls) -> set[str]:
        return {scenario.key for scenario in cls.SCENARIOS}

    @classmethod
    def guarantees(cls) -> set[str]:
        result: set[str] = set()
        for scenario in cls.SCENARIOS:
            result.update(scenario.expected_guarantees)
        return result

    @classmethod
    def validate(cls) -> list[str]:
        problems: list[str] = []
        seen: set[str] = set()
        for scenario in cls.SCENARIOS:
            if not scenario.key or not scenario.concern or not scenario.expected_guarantees:
                problems.append(f"incomplete:{scenario.key or 'unknown'}")
            if scenario.key in seen:
                problems.append(f"duplicate:{scenario.key}")
            seen.add(scenario.key)
        return problems
