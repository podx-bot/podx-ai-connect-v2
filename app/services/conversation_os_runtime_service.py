"""Production runtime gate for PODX Conversation OS.

The gate sits outside legacy/domain conversation runtimes. It loads persistent
conversation state before routing a message, resolves whether the turn is a new
request or a continuation, gives short follow-ups enough active context for the
existing runtimes, and persists the completed turn afterwards.

It is deliberately fail-open: Conversation OS state or extraction failures must
never make the WhatsApp conversation unavailable.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional

from app.services.conversation_kernel import ConversationKernel, ConversationState, TurnKind
from app.services.conversation_state_merge_engine import ConversationStateMergeEngine
from app.services.conversation_topic_resolver import ConversationTopicResolver


class ConversationOSRuntimeService:
    def __init__(
        self,
        delegate,
        ledger_repository,
        request_extractor=None,
        kernel: ConversationKernel | None = None,
        merge_engine: ConversationStateMergeEngine | None = None,
        topic_resolver: ConversationTopicResolver | None = None,
        channel: str = "whatsapp",
    ) -> None:
        self.delegate = delegate
        self.ledger = ledger_repository
        self.request_extractor = request_extractor
        self.kernel = kernel or ConversationKernel()
        self.merge_engine = merge_engine or ConversationStateMergeEngine()
        self.topic_resolver = topic_resolver or ConversationTopicResolver()
        self.channel = str(channel or "whatsapp")

    def process(self, sender_mobile: str, message: str) -> str:
        user_id = str(sender_mobile)
        clean = " ".join(str(message or "").strip().split())
        try:
            state_dict = self.ledger.load_state(user_id) or self._blank_state(user_id)
            state = self._state_from_dict(user_id, state_dict)
            extracted = self._extract_if_useful(clean, state)
            request = extracted.get("request") if extracted.get("success") else None

            topic = self.topic_resolver.resolve(
                state.active_entity,
                clean,
                request if isinstance(request, dict) else None,
            )
            if request and (not state.active_entity or topic == "NEW_TOPIC"):
                state_dict = self._seed_request_state(state_dict, request, clean)
                state = self._state_from_dict(user_id, state_dict)

            decision = self.kernel.resolve(user_id, clean, state)
            if topic == "NEW_TOPIC" and request:
                decision.kind = TurnKind.NEW_TOPIC
                decision.next_action = "route_new_request"
                decision.confidence = max(decision.confidence, float(request.get("confidence") or 0.0))
            elif topic == "CONTINUE" and state.active_entity and decision.kind == TurnKind.NEW_REQUEST:
                # Short natural follow-ups can contain words such as "కావాలి" without
                # being a new demand. Topic continuity is authoritative here.
                decision.kind = TurnKind.UPDATE_EXISTING
                decision.next_action = "merge_active_state"
                decision.confidence = max(decision.confidence, 0.88)

            state_dict = self._merge_followup_facts(state_dict, clean, request, decision.kind)
            routed_message = self._planned_message(clean, state_dict, decision.kind)
            reply = self._delegate(user_id, routed_message)
            validated = self.kernel.validate_reply(decision, reply)
            if validated is None:
                # Do not manufacture an answer. Preserve old behavior as a final
                # fail-open attempt using the exact user text.
                validated = str(self._delegate(user_id, clean) or "").strip()

            final_state = self.merge_engine.merge_state(
                state_dict,
                {
                    "last_user_message": clean,
                    "last_bot_message": validated,
                    "last_bot_intent": decision.kind.value,
                    "pending_action": decision.next_action,
                },
            )
            self.ledger.save_state(user_id, final_state, channel=self.channel)
            self.ledger.append_turn(
                user_id,
                channel=self.channel,
                user_message=clean,
                bot_message=validated,
                turn_kind=decision.kind.value,
                resolved_meaning=decision.resolved_meaning,
                next_action=decision.next_action,
                confidence=decision.confidence,
                state=final_state,
            )
            return validated
        except Exception:
            # Conversation memory is a reliability layer, not a new single point of
            # failure. Existing production routing remains available on any error.
            return self._delegate(user_id, clean)

    def _delegate(self, user_id: str, message: str) -> str:
        try:
            return self.delegate.process(sender_mobile=user_id, message=message)
        except TypeError:
            return self.delegate.process(user_id, message)

    def _extract_if_useful(self, message: str, state: ConversationState) -> Dict[str, Any]:
        if self.request_extractor is None or not message:
            return {"success": False, "request": None}
        # Extraction is most valuable on a new demand or when a user explicitly
        # signals another topic. Avoid an AI call for obvious short follow-ups.
        lowered = message.casefold()
        explicit_switch = any(marker in lowered for marker in self.topic_resolver.NEW_TOPIC_MARKERS)
        obvious_followup = state.active_entity and any(
            marker in lowered for marker in self.topic_resolver.FOLLOWUP_MARKERS
        )
        if obvious_followup and not explicit_switch:
            return {"success": False, "request": None}
        try:
            result = self.request_extractor.extract(message)
            return result if isinstance(result, dict) else {"success": False, "request": None}
        except Exception:
            return {"success": False, "request": None}

    def _seed_request_state(self, state: Dict[str, Any], request: Dict[str, Any], message: str) -> Dict[str, Any]:
        side = str(request.get("side") or "").upper()
        domain = str(request.get("domain") or "").upper()
        subject = str(request.get("subject") or "").strip() or None
        goal = "BUY" if side == "NEED" and domain == "PRODUCT" else side or state.get("goal")
        known = {
            key: request.get(key)
            for key in (
                "side", "domain", "quantity", "unit", "price", "currency",
                "when_text", "location_text", "constraints",
            )
            if request.get(key) not in (None, "", [], {})
        }
        patch = {
            "goal": goal,
            "active_flow": f"{domain}_{side}" if domain and side else state.get("active_flow"),
            "active_entity": subject,
            "known_fields": known,
            "last_user_message": message,
            "pending_action": "route_new_request",
        }
        return self.merge_engine.merge_state(state, patch)

    def _merge_followup_facts(
        self,
        state: Dict[str, Any],
        message: str,
        request: Optional[Dict[str, Any]],
        kind: TurnKind,
    ) -> Dict[str, Any]:
        if kind not in {TurnKind.UPDATE_EXISTING, TurnKind.CLARIFICATION, TurnKind.QUESTION, TurnKind.CONFIRMATION}:
            return state
        patch: Dict[str, Any] = {"last_user_message": message}
        # When a semantic extractor produced compatible facts, merge fields but do
        # not replace the active subject. Empty extracted values cannot erase state.
        if request:
            incoming = {
                key: request.get(key)
                for key in (
                    "quantity", "unit", "price", "currency", "when_text",
                    "location_text", "constraints",
                )
                if request.get(key) not in (None, "", [], {})
            }
            patch["known_fields"] = incoming
        else:
            # Preserve a generic, domain-neutral record of the user's explicit
            # follow-up so downstream tools can use it without hard-coding products.
            known = dict(state.get("known_fields") or {})
            constraints = list(known.get("constraints") or [])
            if message and message not in constraints:
                constraints.append(message)
            patch["known_fields"] = {"constraints": constraints}
        return self.merge_engine.merge_state(state, patch)

    def _planned_message(self, original: str, state: Dict[str, Any], kind: TurnKind) -> str:
        if kind not in {TurnKind.UPDATE_EXISTING, TurnKind.CLARIFICATION, TurnKind.QUESTION, TurnKind.CONFIRMATION}:
            return original
        entity = str(state.get("active_entity") or "current request")
        facts = state.get("known_fields") or {}
        fact_text = self._compact_facts(facts)
        previous = str(state.get("last_bot_message") or "").strip()
        pieces = [f"Continue the existing {entity} request."]
        if fact_text:
            pieces.append(f"Keep known details: {fact_text}.")
        if previous:
            pieces.append(f"Previous PODX reply context: {previous}")
        pieces.append(f"User's new message: {original}")
        return " ".join(pieces)

    @staticmethod
    def _compact_facts(facts: Dict[str, Any]) -> str:
        preferred = (
            "quantity", "unit", "price", "currency", "variant", "quality",
            "when_text", "location_text", "side", "domain",
        )
        values = []
        for key in preferred:
            value = facts.get(key)
            if value not in (None, "", [], {}):
                values.append(f"{key}={value}")
        constraints = facts.get("constraints") or []
        if constraints:
            values.append("constraints=" + "; ".join(str(x) for x in constraints[-3:]))
        return ", ".join(values)

    @staticmethod
    def _blank_state(user_id: str) -> Dict[str, Any]:
        return asdict(ConversationState(user_id=user_id))

    @staticmethod
    def _state_from_dict(user_id: str, data: Dict[str, Any]) -> ConversationState:
        return ConversationState(
            user_id=user_id,
            goal=data.get("goal"),
            active_flow=data.get("active_flow"),
            active_entity=data.get("active_entity"),
            known_fields=dict(data.get("known_fields") or {}),
            missing_fields=list(data.get("missing_fields") or []),
            pending_action=data.get("pending_action"),
            last_bot_message=data.get("last_bot_message"),
            last_bot_intent=data.get("last_bot_intent"),
            expected_reply_type=data.get("expected_reply_type"),
            last_user_message=data.get("last_user_message"),
        )
