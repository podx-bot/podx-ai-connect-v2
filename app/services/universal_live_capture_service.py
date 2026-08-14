"""Live natural-language capture -> match/hold -> target -> notify orchestration."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


class UniversalLiveCaptureService:
    """Turn a natural WhatsApp requirement into the Universal Flow.

    This service is deliberately conservative about when it captures a message.
    Stateful registration/menu flows keep working; natural requirements at the
    main conversation level are handled AI-first.
    """

    GREETINGS = {"hi", "hello", "hey", "హాయ్", "హలో", "నమస్తే", "menu", "మెనూ"}
    COMMAND_PREFIXES = (
        "status ", "accept ", "confirm ", "decline ", "reject ", "cancel ",
        "interested ", "start ", "complete ", "arrived ", "manage ",
    )

    def __init__(
        self,
        extractor,
        demand_repository,
        matcher,
        targeting_service,
        notification_service,
        notification_repository,
        user_repository,
        session_registry,
        min_confidence: float = 0.62,
    ) -> None:
        self.extractor = extractor
        self.demands = demand_repository
        self.matcher = matcher
        self.targeting = targeting_service
        self.notifications = notification_service
        self.notification_repository = notification_repository
        self.users = user_repository
        self.sessions = session_registry
        self.min_confidence = float(min_confidence)

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = " ".join(str(message or "").strip().split())
        if not text or self._skip_text(text):
            return None

        user = self.users.find_by_whatsapp_mobile(sender_mobile) or {}
        if not user or not int(user.get("registration_complete") or 0):
            return None

        session = self.sessions.get(sender_mobile)
        step_name = str(getattr(getattr(session, "step", None), "name", ""))
        if step_name and step_name not in {"MAIN_MENU", "REGISTERED"}:
            return None

        extracted = self.extractor.extract(text)
        if not extracted.get("success"):
            return None
        request = dict(extracted.get("request") or {})
        if not request:
            return None
        if str(request.get("domain") or "OTHER").upper() == "OTHER":
            return None
        if float(request.get("confidence") or 0.0) < self.min_confidence:
            return None

        request["user_id"] = str(sender_mobile)
        request["source"] = "text"
        request["when"] = request.get("when_text")

        if user.get("latitude") is not None and user.get("longitude") is not None:
            request["latitude"] = user.get("latitude")
            request["longitude"] = user.get("longitude")
            request["location_text"] = request.get("location_text") or user.get("location_name") or user.get("area")

        request_id = self.demands.create(request)
        stored = self.demands.get(request_id) or {**request, "id": request_id}

        if stored.get("latitude") is None or stored.get("longitude") is None:
            subject = stored.get("subject") or "మీ requirement"
            return (
                f"✅ '{subject}' requirement save చేశాను. "
                "మీకు దగ్గరలో సరైన match వెతకడానికి Current Location share చేయండి."
            )

        return self._match_target_notify(stored)

    def handle_location(
        self,
        sender_mobile: str,
        latitude: float,
        longitude: float,
        location_name: str | None = None,
        location_address: str | None = None,
    ) -> Optional[str]:
        pending = self.demands.latest_active_for_user_missing_location(sender_mobile)
        if pending is None:
            return None

        location_text = location_name or location_address
        self.users.save_location(
            whatsapp_mobile=sender_mobile,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            location_address=location_address,
        )
        self.demands.update_location(
            demand_id=int(pending["id"]),
            latitude=latitude,
            longitude=longitude,
            location_text=location_text,
        )
        stored = self.demands.get(int(pending["id"])) or pending
        return self._match_target_notify(stored, location_saved=True)

    def _match_target_notify(self, request: Dict[str, Any], location_saved: bool = False) -> str:
        matches = self.matcher.find_matches(request, limit=10)
        if matches:
            targets = [
                {
                    "user_id": str(item.get("user_id") or ""),
                    "score": item.get("score"),
                    "distance_km": item.get("distance_km"),
                }
                for item in matches
                if item.get("user_id")
            ]
            plan = {
                "status": "TARGETED",
                "request_id": request.get("id"),
                "total_targets": len(targets),
                "waves": [{"wave": 1, "radius_km": None, "targets": targets}],
            }
            delivery = self.notifications.dispatch_plan(request, plan)
            prefix = "📍 Location save అయింది. " if location_saved else ""
            return (
                f"{prefix}✅ {len(matches)} సరైన match{'es' if len(matches) != 1 else ''} దొరికాయి. "
                f"వారిలో {delivery.get('sent', 0)} మందికి notification పంపాను. "
                "ఎవరైనా interested అంటే వెంటనే మీకు చెప్తాను."
            )

        already = self.notification_repository.contacted_user_ids(int(request["id"]))
        plan = self.targeting.build_plan(
            request=request,
            already_contacted_user_ids=already,
            per_wave_limit=25,
        )
        if int(plan.get("total_targets") or 0) > 0:
            delivery = self.notifications.dispatch_plan(request, plan)
            prefix = "📍 Location save అయింది. " if location_saved else ""
            return (
                f"{prefix}Direct match ఇప్పుడే లేదు. కానీ సంబంధిత {plan.get('total_targets', 0)} మందిని గుర్తించాను; "
                f"{delivery.get('sent', 0)} మందికి request పంపాను. Response వచ్చిన వెంటనే మీకు చెప్తాను."
            )

        prefix = "📍 Location save అయింది. " if location_saved else ""
        return (
            f"{prefix}మీ request ACTIVEగా ఉంచాను. ఇప్పుడు direct match లేదు. "
            "సంబంధిత వ్యక్తి/product/service దొరికిన వెంటనే మీకు WhatsAppలో చెప్తాను."
        )

    @classmethod
    def _skip_text(cls, text: str) -> bool:
        lowered = text.casefold().strip()
        if lowered in cls.GREETINGS:
            return True
        return any(lowered.startswith(prefix) for prefix in cls.COMMAND_PREFIXES)
