"""Live text/image capture -> match/hold -> target -> notify orchestration."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


class UniversalLiveCaptureService:
    GREETINGS = {"hi", "hello", "hey", "హాయ్", "హలో", "నమస్తే", "menu", "మెనూ"}
    COMMAND_PREFIXES = (
        "status ", "accept ", "confirm ", "decline ", "reject ", "cancel ",
        "interested ", "start ", "complete ", "arrived ", "manage ",
        "buy_interested ", "buy_not_interested ", "seller_confirm ",
        "seller_decline ", "order_continue ", "direct_talk ",
    )
    QUANTITY_FOLLOWUP_RE = re.compile(
        r"(?<![\w.])(?P<quantity>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>kg|kgs|kilo(?:gram)?s?|కిలోలు?|కిలో|కేజీలు?|కేజీ|किलो)",
        re.IGNORECASE,
    )
    QUANTITY_FOLLOWUP_FILLERS = {
        "", "కావాలి", "నాకు కావాలి", "చాలు", "సరిపోతుంది",
        "please", "want", "need", "i want", "i need", "want it", "need it",
        "चाहिए", "मुझे चाहिए",
    }
    VARIANT_FOLLOWUPS = {
        "boneless": "boneless",
        "బోన్లెస్": "boneless",
        "బోన్‌లెస్": "boneless",
        "बोनलेस": "boneless",
        "skinless": "skinless",
        "స్కిన్‌లెస్": "skinless",
        "స్కిన్లెస్": "skinless",
        "स्किनलेस": "skinless",
    }
    VARIANT_FOLLOWUP_FILLERS = {
        "", "కావాలి", "నాకు కావాలి", "చాలు", "సరిపోతుంది",
        "please", "want", "need", "i want", "i need", "want it", "need it",
        "చేయండి", "ఉండాలి", "चाहिए", "मुझे चाहिए",
    }
    LOCATION_PREFIXES = ("in ", "at ", "near ", "around ", "area ")
    LOCATION_BLOCK_WORDS = {
        "want", "need", "buy", "sell", "job", "work", "service", "ride",
        "price", "budget", "delivery", "today", "tomorrow", "urgent",
        "available", "availability", "quantity", "size", "weight",
        "కావాలి", "కొనాలి", "అమ్మాలి", "పని", "ఉద్యోగం", "సర్వీస్",
        "ధర", "రేట్", "ఈరోజు", "రేపు", "అర్జెంట్",
    }

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

        quantity_followup = self._quantity_followup(text)
        if quantity_followup is not None:
            reply = self._revise_latest_quantity(
                sender_mobile=sender_mobile,
                quantity=quantity_followup[0],
                unit=quantity_followup[1],
            )
            if reply is not None:
                return reply

        variant_followup = self._variant_followup(text)
        if variant_followup is not None:
            reply = self._revise_latest_constraint(
                sender_mobile=sender_mobile,
                key="variant",
                value=variant_followup,
            )
            if reply is not None:
                return reply

        location_reply = self._merge_location_text_followup(sender_mobile, text)
        if location_reply is not None:
            return location_reply

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

    def _merge_location_text_followup(self, sender_mobile: str, text: str) -> Optional[str]:
        pending = self.demands.latest_active_for_user_missing_location(sender_mobile)
        if pending is None:
            return None
        location_text = self._location_text_followup(text)
        if location_text is None:
            return None
        updater = getattr(self.demands, "update_location_text", None)
        if not callable(updater):
            return None
        updater(int(pending["id"]), location_text)
        stored = self.demands.get(int(pending["id"])) or {**pending, "location_text": location_text}
        subject = str(stored.get("subject") or "మీ requirement")
        self._trigger_demand_intelligence(stored)
        result = self._match_target_notify(stored)
        return (
            f"📍 {location_text} locationని '{subject}' requirementకి add చేశాను. "
            "ముందు చెప్పిన requirement అలాగే ఉంచాను.\n"
            f"{result}\n"
            "Exact distance ranking కోసం కావాలంటే Current Location కూడా share చేయండి."
        )

    def _revise_latest_quantity(self, sender_mobile: str, quantity: float, unit: str) -> Optional[str]:
        latest = getattr(self.demands, "latest_active_for_user", None)
        if not callable(latest):
            return None
        previous = latest(sender_mobile)
        if previous is None:
            return None

        revised = {
            "user_id": str(sender_mobile),
            "side": previous.get("side"),
            "domain": previous.get("domain"),
            "subject": previous.get("subject"),
            "quantity": float(quantity),
            "unit": unit,
            "price": previous.get("price"),
            "currency": previous.get("currency"),
            "when_text": previous.get("when_text"),
            "latitude": previous.get("latitude"),
            "longitude": previous.get("longitude"),
            "location_text": previous.get("location_text"),
            "constraints": previous.get("constraints") or {},
            "source": "text",
            "media_ref": None,
            "status": "ACTIVE",
        }
        request_id = self.demands.create(revised)
        self.demands.update_status(int(previous["id"]), "REVISED")
        stored = self.demands.get(request_id) or {**revised, "id": request_id}
        subject = str(stored.get("subject") or "మీ requirement")
        quantity_text = f"{float(quantity):g} {unit}"

        if stored.get("latitude") is None or stored.get("longitude") is None:
            return (
                f"🔄 {subject} quantity {quantity_text}కి update చేశాను. "
                "మీకు దగ్గరలో సరైన match వెతకడానికి Current Location share చేయండి."
            )

        self._trigger_demand_intelligence(stored)
        result = self._match_target_notify(stored)
        return f"🔄 {subject} quantity {quantity_text}కి update చేశాను.\n{result}"

    def _revise_latest_constraint(self, sender_mobile: str, key: str, value: str) -> Optional[str]:
        latest = getattr(self.demands, "latest_active_for_user", None)
        if not callable(latest):
            return None
        previous = latest(sender_mobile)
        if previous is None or str(previous.get("domain") or "").upper() != "PRODUCT":
            return None

        raw_constraints = previous.get("constraints")
        if isinstance(raw_constraints, dict):
            constraints = dict(raw_constraints)
        elif isinstance(raw_constraints, list):
            constraints = {"preferences": list(raw_constraints)} if raw_constraints else {}
        else:
            constraints = {}
        constraints[str(key)] = str(value)

        revised = {
            "user_id": str(sender_mobile),
            "side": previous.get("side"),
            "domain": previous.get("domain"),
            "subject": previous.get("subject"),
            "quantity": previous.get("quantity"),
            "unit": previous.get("unit"),
            "price": previous.get("price"),
            "currency": previous.get("currency"),
            "when_text": previous.get("when_text"),
            "latitude": previous.get("latitude"),
            "longitude": previous.get("longitude"),
            "location_text": previous.get("location_text"),
            "constraints": constraints,
            "source": "text",
            "media_ref": None,
            "status": "ACTIVE",
        }
        request_id = self.demands.create(revised)
        self.demands.update_status(int(previous["id"]), "REVISED")
        stored = self.demands.get(request_id) or {**revised, "id": request_id}
        subject = str(stored.get("subject") or "మీ requirement")

        if stored.get("latitude") is None or stored.get("longitude") is None:
            return (
                f"🔄 {subject} requestకి {value} preference add చేశాను. "
                "ముందు చెప్పిన quantity/details అలాగే ఉంచాను. Match కోసం Current Location share చేయండి."
            )

        self._trigger_demand_intelligence(stored)
        result = self._match_target_notify(stored)
        return (
            f"🔄 {subject} requestకి {value} preference add చేశాను. "
            f"ముందు చెప్పిన quantity/details అలాగే ఉంచాను.\n{result}"
        )

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

    @staticmethod
    def _is_app_request(request: Dict[str, Any]) -> bool:
        return str(request.get("user_id") or "").strip().casefold().startswith("app-")

    def _match_target_notify(self, request: Dict[str, Any], location_saved: bool = False) -> str:
        prefix = "📍 Location save అయింది. " if location_saved else ""
        app_request = self._is_app_request(request)
        matches = self.matcher.find_matches(request, limit=10)
        if matches:
            targets = [{"user_id": str(item.get("user_id") or ""), "score": item.get("score"),
                        "distance_km": item.get("distance_km")}
                       for item in matches if item.get("user_id") and str(item.get("user_id")) != str(request.get("user_id"))]
            side = str(request.get("side") or "").upper()

            # App-originated requests use an internal app-* identity, not a WhatsApp
            # phone number. Never send buyer match cards to Meta using that identity.
            # The app receives the match result in this response; seller WhatsApp
            # outreach belongs to the later explicit interest/confirmation stage.
            if app_request:
                if side == "NEED":
                    return (
                        f"{prefix}✅ {len(targets)} seller match{'es' if len(targets) != 1 else ''} దొరికాయి. "
                        "Match result ASKODOX appలో readyగా ఉంది. నచ్చిన sellerపై Interested ఎంచుకున్న తర్వాత sellerకి notification వెళ్తుంది."
                    )
                return (
                    f"{prefix}✅ {len(targets)} buyer match{'es' if len(targets) != 1 else ''} దొరికాయి. "
                    "Match result ASKODOX appలో readyగా ఉంది. Buyer selection తర్వాత next notification flow కొనసాగుతుంది."
                )

            plan = {"status": "TARGETED", "request_id": request.get("id"), "total_targets": len(targets),
                    "waves": [{"wave": 1, "radius_km": None, "targets": targets}]}
            delivery = self.notifications.dispatch_plan(request, plan)
            sent = int(delivery.get("sent") or 0)
            failed = int(delivery.get("failed") or 0)
            skipped = int(delivery.get("skipped_duplicate") or 0)
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
        total_targets = int(plan.get("total_targets") or 0)
        if total_targets > 0:
            if app_request:
                return (
                    f"{prefix}Direct match ఇప్పుడే లేదు. కానీ {total_targets} relevant candidate"
                    f"{'s' if total_targets != 1 else ''} దొరికారు. ASKODOX appలో request ACTIVEగా ఉంది; "
                    "exact match/availability confirm అయిన వెంటనే result update అవుతుంది."
                )

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

        channel = "ASKODOX appలో" if app_request else "WhatsAppలో"
        return (f"{prefix}మీ request ACTIVEగా ఉంచాను. ఇప్పుడు direct match లేదు. "
                f"సంబంధిత వ్యక్తి/product/service దొరికిన వెంటనే మీకు {channel} చెప్తాను.")

    @classmethod
    def _quantity_followup(cls, text: str) -> Optional[tuple[float, str]]:
        match = cls.QUANTITY_FOLLOWUP_RE.search(str(text or ""))
        if match is None:
            return None
        remaining = f"{text[:match.start()]} {text[match.end():]}"
        remaining = " ".join(remaining.casefold().split()).strip(" .,!?:;")
        allowed = {item.casefold().strip(" .,!?:;") for item in cls.QUANTITY_FOLLOWUP_FILLERS}
        if remaining not in allowed:
            return None
        quantity = float(match.group("quantity"))
        if quantity <= 0:
            return None
        return quantity, "kg"

    @classmethod
    def _variant_followup(cls, text: str) -> Optional[str]:
        normalized = " ".join(str(text or "").casefold().split()).strip(" .,!?:;")
        allowed_fillers = {
            item.casefold().strip(" .,!?:;") for item in cls.VARIANT_FOLLOWUP_FILLERS
        }
        for phrase, canonical in sorted(cls.VARIANT_FOLLOWUPS.items(), key=lambda item: len(item[0]), reverse=True):
            phrase_low = phrase.casefold()
            if phrase_low not in normalized:
                continue
            remaining = normalized.replace(phrase_low, " ", 1)
            remaining = " ".join(remaining.split()).strip(" .,!?:;")
            if remaining in allowed_fillers:
                return canonical
        return None

    @classmethod
    def _location_text_followup(cls, text: str) -> Optional[str]:
        value = " ".join(str(text or "").strip().split()).strip(" .,!?:;")
        if not value or len(value) > 80 or any(ch.isdigit() for ch in value):
            return None
        lowered = value.casefold()
        for prefix in cls.LOCATION_PREFIXES:
            if lowered.startswith(prefix):
                value = value[len(prefix):].strip(" .,!?:;")
                lowered = value.casefold()
                break
        if not value or len(value.split()) > 6:
            return None
        tokens = set(re.findall(r"[\w]+", lowered, flags=re.UNICODE))
        if tokens & cls.LOCATION_BLOCK_WORDS:
            return None
        return value

    @classmethod
    def _skip_text(cls, text: str) -> bool:
        lowered = text.casefold().strip()
        if lowered in cls.GREETINGS:
            return True
        return any(lowered.startswith(prefix) for prefix in cls.COMMAND_PREFIXES)