"""Live text/image capture -> match/hold -> target -> notify orchestration."""

from __future__ import annotations

from typing import Any, Dict, Optional


class UniversalLiveCaptureService:
    GREETINGS = {"hi", "hello", "hey", "హాయ్", "హలో", "నమస్తే", "menu", "మెనూ"}
    COMMAND_PREFIXES = (
        "status ", "accept ", "confirm ", "decline ", "reject ", "cancel ",
        "interested ", "start ", "complete ", "arrived ", "manage ",
        "buy_interested ", "buy_not_interested ", "seller_confirm ",
        "seller_decline ", "order_continue ", "direct_talk ",
    )

    def __init__(self, extractor, demand_repository, matcher, targeting_service,
                 notification_service, notification_repository, user_repository,
                 session_registry, min_confidence: float = 0.62, demand_intelligence=None) -> None:
        self.extractor = extractor
        self.demands = demand_repository
        self.matcher = matcher
        self.targeting = targeting_service
        self.notifications = notification_service
        self.notification_repository = notification_repository
        self.users = user_repository
        self.sessions = session_registry
        self.min_confidence = float(min_confidence)
        self.demand_intelligence = demand_intelligence

    def process_text(self, sender_mobile: str, message: str) -> Optional[str]:
        text = " ".join(str(message or "").strip().split())
        if not text or self._skip_text(text):
            return None
        if not self._can_capture(sender_mobile):
            return None
        extracted = self.extractor.extract(text)
        if not extracted.get("success"):
            return None
        request = dict(extracted.get("request") or {})
        if not request:
            return None
        return self.process_structured(sender_mobile=sender_mobile, request=request, source="text")

    def process_structured(self, sender_mobile: str, request: Dict[str, Any],
                           source: str = "text", media_ref: str | None = None) -> Optional[str]:
        if not self._can_capture(sender_mobile):
            return None
        request = dict(request or {})
        if str(request.get("side") or "").upper() not in {"NEED", "OFFER"}:
            return None
        if str(request.get("domain") or "OTHER").upper() == "OTHER":
            return None
        if not str(request.get("subject") or "").strip():
            return None
        if float(request.get("confidence") or 0.0) < self.min_confidence:
            return None

        user = self.users.find_by_whatsapp_mobile(sender_mobile) or {}
        request["user_id"] = str(sender_mobile)
        request["source"] = str(source or "text")
        request["media_ref"] = media_ref
        request["when"] = request.get("when") or request.get("when_text")
        if user.get("latitude") is not None and user.get("longitude") is not None:
            request["latitude"] = user.get("latitude")
            request["longitude"] = user.get("longitude")
            request["location_text"] = request.get("location_text") or user.get("location_name") or user.get("area")

        request_id = self.demands.create(request)
        stored = self.demands.get(request_id) or {**request, "id": request_id}
        if stored.get("latitude") is None or stored.get("longitude") is None:
            subject = stored.get("subject") or "మీ requirement"
            return f"✅ '{subject}' requirement save చేశాను. మీకు దగ్గరలో సరైన match వెతకడానికి Current Location share చేయండి."
        self._trigger_demand_intelligence(stored)
        return self._match_target_notify(stored)

    def handle_location(self, sender_mobile: str, latitude: float, longitude: float,
                        location_name: str | None = None, location_address: str | None = None) -> Optional[str]:
        pending = self.demands.latest_active_for_user_missing_location(sender_mobile)
        if pending is None:
            return None
        location_text = location_name or location_address
        self.users.save_location(whatsapp_mobile=sender_mobile, latitude=latitude, longitude=longitude,
                                 location_name=location_name, location_address=location_address)
        self.demands.update_location(demand_id=int(pending["id"]), latitude=latitude, longitude=longitude,
                                     location_text=location_text)
        stored = self.demands.get(int(pending["id"])) or pending
        self._trigger_demand_intelligence(stored)
        return self._match_target_notify(stored, location_saved=True)

    def _trigger_demand_intelligence(self, request: Dict[str, Any]) -> None:
        if self.demand_intelligence is None:
            return
        if str(request.get("side") or "").upper() != "NEED":
            return
        try:
            self.demand_intelligence.trigger_async()
        except Exception:
            return

    def _can_capture(self, sender_mobile: str) -> bool:
        user = self.users.find_by_whatsapp_mobile(sender_mobile) or {}
        if not user or not int(user.get("registration_complete") or 0):
            return False
        session = self.sessions.get(sender_mobile)
        step_name = str(getattr(getattr(session, "step", None), "name", ""))
        return not step_name or step_name in {"MAIN_MENU", "REGISTERED"}

    def _match_target_notify(self, request: Dict[str, Any], location_saved: bool = False) -> str:
        prefix = "📍 Location save అయింది. " if location_saved else ""
        matches = self.matcher.find_matches(request, limit=10)
        if matches:
            targets = [{"user_id": str(item.get("user_id") or ""), "score": item.get("score"),
                        "distance_km": item.get("distance_km")}
                       for item in matches if item.get("user_id") and str(item.get("user_id")) != str(request.get("user_id"))]
            plan = {"status": "TARGETED", "request_id": request.get("id"), "total_targets": len(targets),
                    "waves": [{"wave": 1, "radius_km": None, "targets": targets}]}
            delivery = self.notifications.dispatch_plan(request, plan)
            sent = int(delivery.get("sent") or 0)
            failed = int(delivery.get("failed") or 0)
            skipped = int(delivery.get("skipped_duplicate") or 0)
            side = str(request.get("side") or "").upper()
            if sent > 0:
                if side == "NEED":
                    return (f"{prefix}✅ {len(matches)} seller match{'es' if len(matches) != 1 else ''} దొరికాయి. "
                            f"{sent} notification option{'s' if sent != 1 else ''} మీకు పంపాను. నచ్చిన sellerపై 'ఆసక్తి ఉంది' నొక్కండి.")
                return (f"{prefix}✅ {len(matches)} buyer match{'es' if len(matches) != 1 else ''} దొరికాయి. "
                        f"{sent} buyer notification{'s' if sent != 1 else ''}కి మీ offer పంపాను. Buyer ఆసక్తి చూపితే మీకు Confirm వస్తుంది.")
            if failed > 0:
                return (f"{prefix}✅ సరైన match దొరికింది, కానీ WhatsApp notification delivery ప్రస్తుతం fail అయింది. "
                        "మీ request ACTIVEగా ఉంది; deliveryని మళ్లీ ప్రయత్నించవచ్చు.")
            if skipped > 0:
                return (f"{prefix}✅ ఈ match options ఇప్పటికే పంపబడ్డాయి. "
                        "మీ request ACTIVEగా ఉంది; response కోసం చూస్తున్నాను.")
            return (f"{prefix}మీ request ACTIVEగా ఉంచాను. Match record ఉంది కానీ కొత్త eligible recipient లేదు. "
                    "కొత్త match దొరికిన వెంటనే WhatsAppలో చెప్తాను.")

        already = self.notification_repository.contacted_user_ids(int(request["id"]))
        plan = self.targeting.build_plan(request=request, already_contacted_user_ids=already, per_wave_limit=25)
        if int(plan.get("total_targets") or 0) > 0:
            delivery = self.notifications.dispatch_plan(request, plan)
            sent = int(delivery.get("sent") or 0)
            failed = int(delivery.get("failed") or 0)
            if sent > 0:
                side = str(request.get("side") or "").upper()
                if side == "NEED":
                    return (f"{prefix}Direct match ఇప్పుడే లేదు. కానీ {sent} relevant seller notification option{'s' if sent != 1 else ''} "
                            "మీకు పంపాను. Interested sellerని select చేయండి.")
                return (f"{prefix}Direct match ఇప్పుడే లేదు. కానీ సంబంధిత {sent} buyer notification{'s' if sent != 1 else ''}కి "
                        "మీ offer పంపాను. Response వచ్చిన వెంటనే మీకు చెప్తాను.")
            if failed > 0:
                return (f"{prefix}సంబంధిత users దొరికారు, కానీ WhatsApp delivery ప్రస్తుతం fail అయింది. "
                        "మీ request ACTIVEగా ఉంచాను.")

        return (f"{prefix}మీ request ACTIVEగా ఉంచాను. ఇప్పుడు direct match లేదు. "
                "సంబంధిత వ్యక్తి/product/service దొరికిన వెంటనే మీకు WhatsAppలో చెప్తాను.")

    @classmethod
    def _skip_text(cls, text: str) -> bool:
        lowered = text.casefold().strip()
        if lowered in cls.GREETINGS:
            return True
        return any(lowered.startswith(prefix) for prefix in cls.COMMAND_PREFIXES)
