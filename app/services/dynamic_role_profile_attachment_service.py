"""Intent-driven PODX role/capability attachment.

Universal registration stays role-neutral. Once a registered user expresses a
clear business intent, this wrapper derives the matching durable capability from
the UniversalCategoryFlowBrain and attaches it before the normal domain runtime
continues. It never asks an up-front role menu and never blocks the downstream
conversation.
"""
from __future__ import annotations


class DynamicRoleProfileAttachmentService:
    ROLE_MAP = {
        ("COMMERCE", "SEEKER"): "BUYER",
        ("COMMERCE", "PROVIDER"): "SELLER",
        ("SERVICES", "SEEKER"): "SERVICE_CUSTOMER",
        ("SERVICES", "PROVIDER"): "SERVICE_PROVIDER",
        ("JOBS", "SEEKER"): "WORKER",
        ("JOBS", "PROVIDER"): "EMPLOYER",
    }

    def __init__(
        self,
        delegate,
        category_brain,
        user_repository,
        min_confidence: float = 0.75,
        profile_essentials=None,
        session_registry=None,
    ) -> None:
        self.delegate = delegate
        self.category_brain = category_brain
        self.user_repository = user_repository
        self.min_confidence = float(min_confidence)
        self.profile_essentials = profile_essentials
        self.session_registry = session_registry

    def process(self, sender_mobile: str, message: str) -> str:
        clean = str(message or "").strip()
        self._attach_for_intent(sender_mobile, clean)
        return self._call_delegate(sender_mobile, clean)

    def _attach_for_intent(self, sender_mobile: str, message: str) -> None:
        try:
            user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
            if not user or int(user.get("registration_complete") or 0) != 1:
                return

            decision = self.category_brain.classify(message)
            confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
            if confidence < self.min_confidence:
                return

            category = str(getattr(decision, "category", "") or "").upper()
            side = str(getattr(decision, "side", "") or "").upper()
            capability = self.ROLE_MAP.get((category, side))
            if not capability:
                return

            has_capability = getattr(self.user_repository, "has_capability", None)
            already_attached = callable(has_capability) and has_capability(sender_mobile, capability)
            if not already_attached:
                self.user_repository.add_capability(
                    sender_mobile,
                    capability,
                    source="intent_auto_attach",
                )

            self._record_profile_plan(sender_mobile, capability)
        except Exception:
            # Capability/profile enrichment must never cause a user message to fail.
            return

    def _record_profile_plan(self, sender_mobile: str, capability: str) -> None:
        planner = self.profile_essentials
        sessions = self.session_registry
        if planner is None or sessions is None:
            return
        try:
            plan = planner.plan_for_user(sender_mobile, capability)
            session = sessions.get(sender_mobile)
            data = getattr(session, "data", None)
            if not isinstance(data, dict):
                return
            data["active_capability"] = capability
            data["role_profile_missing_fields"] = list(plan.missing_fields)
            data["role_profile_complete"] = bool(plan.complete)
            save = getattr(sessions, "save", None)
            if callable(save):
                save(sender_mobile)
        except Exception:
            return

    def _call_delegate(self, sender_mobile: str, message: str) -> str:
        process = getattr(self.delegate, "process", None)
        if callable(process):
            return process(sender_mobile, message)
        if callable(self.delegate):
            return self.delegate(sender_mobile, message)
        return ""
