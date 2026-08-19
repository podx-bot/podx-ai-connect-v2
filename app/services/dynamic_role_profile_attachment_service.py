"""Intent-driven PODX role/capability attachment.

Universal registration stays role-neutral. Once a registered user expresses a
clear business intent, this wrapper derives the matching durable capability from
the UniversalCategoryFlowBrain and attaches it before the normal domain runtime
continues. It never asks an up-front role menu and never blocks the downstream
conversation.
"""
from __future__ import annotations

from app.models.session import ConversationStep
from app.services.smart_job_message_service import SmartJobMessageService


class DynamicRoleProfileAttachmentService:
    ROLE_MAP = {
        ("COMMERCE", "SEEKER"): "BUYER",
        ("COMMERCE", "PROVIDER"): "SELLER",
        ("SERVICES", "SEEKER"): "SERVICE_CUSTOMER",
        ("SERVICES", "PROVIDER"): "SERVICE_PROVIDER",
        ("JOBS", "SEEKER"): "WORKER",
        ("JOBS", "PROVIDER"): "EMPLOYER",
    }

    def __init__(self, delegate, category_brain, user_repository, min_confidence: float = 0.75, profile_essentials=None, session_registry=None, smart_job_message_service=None) -> None:
        self.delegate = delegate
        self.category_brain = category_brain
        self.user_repository = user_repository
        self.min_confidence = float(min_confidence)
        self.profile_essentials = profile_essentials
        self.session_registry = session_registry
        self.smart_job_message_service = smart_job_message_service or SmartJobMessageService()

    def process(self, sender_mobile: str, message: str) -> str:
        clean = str(message or "").strip()
        intent_context = self._attach_for_intent(sender_mobile, clean)
        self._prefill_worker_slots(sender_mobile, clean, intent_context)
        resume_prompt = self._resume_missing_profile(sender_mobile, intent_context)
        if resume_prompt is not None:
            return resume_prompt
        return self._call_delegate(sender_mobile, clean)

    def _attach_for_intent(self, sender_mobile: str, message: str):
        try:
            user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
            if not user or int(user.get("registration_complete") or 0) != 1:
                return None
            decision = self.category_brain.classify(message)
            confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
            if confidence < self.min_confidence:
                return None
            category = str(getattr(decision, "category", "") or "").upper()
            side = str(getattr(decision, "side", "") or "").upper()
            capability = self.ROLE_MAP.get((category, side))
            if not capability:
                return None
            has_capability = getattr(self.user_repository, "has_capability", None)
            already_attached = callable(has_capability) and has_capability(sender_mobile, capability)
            if not already_attached:
                self.user_repository.add_capability(sender_mobile, capability, source="intent_auto_attach")
            plan = self._record_profile_plan(sender_mobile, capability)
            return {"capability": capability, "user": user, "plan": plan}
        except Exception:
            return None

    def _record_profile_plan(self, sender_mobile: str, capability: str):
        planner = self.profile_essentials
        sessions = self.session_registry
        if planner is None:
            return None
        try:
            plan = planner.plan_for_user(sender_mobile, capability)
            if sessions is not None:
                session = sessions.get(sender_mobile)
                data = getattr(session, "data", None)
                if isinstance(data, dict):
                    data["active_capability"] = capability
                    data["role_profile_missing_fields"] = list(plan.missing_fields)
                    data["role_profile_complete"] = bool(plan.complete)
                    save = getattr(sessions, "save", None)
                    if callable(save):
                        save(sender_mobile)
            return plan
        except Exception:
            return None

    def _prefill_worker_slots(self, sender_mobile: str, message: str, intent_context) -> None:
        if not intent_context or intent_context.get("capability") != "WORKER" or self.session_registry is None:
            return
        try:
            details = self.smart_job_message_service.extract(message)
            session = self.session_registry.get(sender_mobile)
            data = getattr(session, "data", None)
            if not isinstance(data, dict):
                return
            user = intent_context.get("user") or {}
            data["role"] = "WORKER"
            category = details.get("category") or user.get("job_category") or data.get("category")
            experience = details.get("experience") or user.get("experience") or data.get("experience")
            availability = details.get("availability") or user.get("availability") or data.get("availability")
            if category:
                data["category"] = category
            if experience:
                data["experience"] = experience
            if availability:
                data["availability"] = availability
            save_worker = getattr(self.user_repository, "save_worker_profile", None)
            if category and experience and availability and callable(save_worker):
                save_worker(whatsapp_mobile=sender_mobile, category=category, experience=experience, availability=availability)
                refreshed = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
                if refreshed:
                    intent_context["user"] = refreshed
                intent_context["plan"] = self._record_profile_plan(sender_mobile, "WORKER")
            save_session = getattr(self.session_registry, "save", None)
            if callable(save_session):
                save_session(sender_mobile)
        except Exception:
            return

    def _resume_missing_profile(self, sender_mobile: str, intent_context) -> str | None:
        """Resume only the first genuinely missing durable worker field.

        Category discovery is deliberately open-ended: examples and fixed menus can
        anchor users and classifiers to a small taxonomy. PODX asks for the user's
        own words, then the intent/schema layer classifies the answer dynamically.
        """
        if not intent_context or self.session_registry is None or intent_context.get("capability") != "WORKER":
            return None
        try:
            session = self.session_registry.get(sender_mobile)
            data = getattr(session, "data", None)
            if not isinstance(data, dict):
                return None
            user = intent_context.get("user") or {}
            data["role"] = "WORKER"
            if user.get("job_category") and not data.get("category"):
                data["category"] = user["job_category"]
            if user.get("experience") and not data.get("experience"):
                data["experience"] = user["experience"]
            if user.get("availability") and not data.get("availability"):
                data["availability"] = user["availability"]
            missing = []
            if not data.get("category"):
                missing.append("job_category")
            if not data.get("experience"):
                missing.append("experience")
            if not data.get("availability"):
                missing.append("availability")
            if user.get("latitude") is None or user.get("longitude") is None:
                missing.append("location")
            data["role_profile_missing_fields"] = list(missing)
            data["role_profile_complete"] = not missing
            if not missing:
                return None
            first = missing[0]
            if first == "job_category":
                session.step = ConversationStep.WORKER_CATEGORY
                prompt = "మీకు ఏ పని కావాలో మీ మాటల్లో చెప్పండి — voiceగా లేదా textగా."
            elif first == "experience":
                session.step = ConversationStep.WORKER_EXPERIENCE
                prompt = "మీ Experience ఎంత?\n1. Fresher\n2. 1-2 Years\n3. 3-5 Years\n4. 5+ Years"
            elif first == "availability":
                session.step = ConversationStep.WORKER_AVAILABILITY
                prompt = "మీ Availability ఎప్పుడు?\n1. Today\n2. Tomorrow\n3. This Week"
            elif first == "location":
                session.step = ConversationStep.WORKER_LOCATION
                prompt = "📍 మీ Worker profileలో Location మాత్రమే కావాలి. WhatsApp Attachment ద్వారా Current Location share చేయండి."
            else:
                return None
            save = getattr(self.session_registry, "save", None)
            if callable(save):
                save(sender_mobile)
            return prompt
        except Exception:
            return None

    def _call_delegate(self, sender_mobile: str, message: str) -> str:
        process = getattr(self.delegate, "process", None)
        if callable(process):
            return process(sender_mobile, message)
        if callable(self.delegate):
            return self.delegate(sender_mobile, message)
        return ""
