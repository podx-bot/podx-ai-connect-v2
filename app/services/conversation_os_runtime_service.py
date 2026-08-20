"""Production runtime gate for PODX Conversation OS.

This layer must never add a second blocking AI call on the synchronous WhatsApp
reply path. It keeps durable turn context around the existing production runtime
and enriches short follow-ups from the previous user/PODX turn.
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

            # Never require semantic extraction to create a reply. On the WhatsApp
            # hot path, continuity is resolved from durable state + raw prior turn.
            topic = self.topic_resolver.resolve(state.active_entity, clean, None)
            decision = self.kernel.resolve(user_id, clean, state)
            if topic == "CONTINUE" and state.active_entity and decision.kind == TurnKind.NEW_REQUEST:
                decision.kind = TurnKind.UPDATE_EXISTING
                decision.next_action = "merge_active_state"
                decision.confidence = max(decision.confidence, 0.88)

            state_dict = self._merge_followup_facts(state_dict, clean, None, decision.kind)
            routed_message = self._planned_message(clean, state_dict, decision.kind)
            reply = self._delegate(user_id, routed_message)
            validated = self.kernel.validate_reply(decision, reply)
            if validated is None:
                validated = str(self._delegate(user_id, clean) or "").strip()

            # A new request must replace the durable request anchor. Otherwise a
            # correctly routed new turn can still leave the previous subject in
            # memory and poison the following message. Keep the generic active
            # conversation envelope, but reset request-specific remembered facts.
            if decision.kind in {TurnKind.NEW_REQUEST, TurnKind.NEW_TOPIC} and clean:
                state_dict = self.merge_engine.merge_state(
                    state_dict,
                    {
                        "active_flow": "ACTIVE_CONVERSATION",
                        "active_entity": "current request",
                        "known_fields": {
                            "request_text": clean,
                            "constraints": [],
                        },
                        "missing_fields": [],
                        "expected_reply_type": None,
                    },
                )
            # A successful first turn becomes the durable conversation anchor even
            # without an extra model call. This is enough for short follow-ups such
            # as "బోన్లెస్ కావాలి" and "రేట్ ఎంత?" to retain the original request.
            elif not state_dict.get("active_entity") and clean:
                state_dict = self.merge_engine.merge_state(
                    state_dict,
                    {
                        "active_flow": "ACTIVE_CONVERSATION",
                        "active_entity": "current request",
                        "known_fields": {"request_text": clean},
                    },
                )

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
            # Memory is a reliability layer, never a single point of failure.
            return self._delegate(user_id, clean)

    def _delegate(self, user_id: str, message: str) -> str:
        try:
            return self.delegate.process(sender_mobile=user_id, message=message)
        except TypeError:
            return self.delegate.process(user_id, message)

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
        previous_user = str(facts.get("request_text") or "").strip()
        previous_bot = str(state.get("last_bot_message") or "").strip()
        pieces = [f"Continue the existing {entity}."]
        if previous_user:
            pieces.append(f"Original user request: {previous_user}")
        if fact_text:
            pieces.append(f"Keep known details: {fact_text}.")
        if previous_bot:
            pieces.append(f"Previous PODX reply context: {previous_bot}")
        pieces.append(f"User's new message: {original}")
        return " ".join(pieces)

    @staticmethod
    def _compact_facts(facts: Dict[str, Any]) -> str:
        preferred = (
            "request_text", "quantity", "unit", "price", "currency", "variant",
            "quality", "when_text", "location_text", "side", "domain",
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
