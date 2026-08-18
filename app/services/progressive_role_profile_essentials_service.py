"""Missing-only durable role profile planning for PODX.

This module separates durable profile essentials from request/listing/deal fields.
It never asks users to pre-fill every possible role. Instead it exposes the next
missing durable fields for the role inferred from real intent.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleProfilePlan:
    capability: str
    missing_fields: tuple[str, ...]
    complete: bool


class ProgressiveRoleProfileEssentialsService:
    """Compute only durable profile fields that are actually missing.

    Buyer, seller, service-customer, service-provider and employer transaction
    details are intentionally left to their vertical request/listing flows. The
    current shared user schema has durable worker fields, so those are planned
    here without forcing re-entry when already saved.
    """

    DURABLE_FIELDS = {
        "BUYER": (),
        "SELLER": (),
        "SERVICE_CUSTOMER": (),
        "SERVICE_PROVIDER": (),
        "WORKER": ("job_category", "experience", "availability", "location"),
        "EMPLOYER": (),
    }

    def __init__(self, user_repository) -> None:
        self.user_repository = user_repository

    def plan_for_user(self, sender_mobile: str, capability: str) -> RoleProfilePlan:
        role = str(capability or "").upper()
        required = self.DURABLE_FIELDS.get(role, ())
        if not required:
            return RoleProfilePlan(role, (), True)

        try:
            user = self.user_repository.find_by_whatsapp_mobile(sender_mobile) or {}
        except Exception:
            user = {}

        missing = tuple(field for field in required if self._missing(user, field))
        return RoleProfilePlan(role, missing, not missing)

    @staticmethod
    def _missing(user: dict, field: str) -> bool:
        if field == "location":
            return user.get("latitude") is None or user.get("longitude") is None
        value = user.get(field)
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        return False
