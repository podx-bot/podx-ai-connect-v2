"""State merge rules for PODX Conversation OS."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable


class ConversationStateMergeEngine:
    """Merge only newly supplied facts while preserving active context.

    Latest explicit values win. Unknown/empty values never erase known facts.
    Domain runtimes may pass a field allowlist to keep merges scoped.
    """

    EMPTY = (None, "", [], {})

    def merge_fields(
        self,
        current: Dict[str, Any] | None,
        incoming: Dict[str, Any] | None,
        *,
        allowed_fields: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        merged = deepcopy(current or {})
        allowed = set(allowed_fields) if allowed_fields is not None else None
        for key, value in (incoming or {}).items():
            if allowed is not None and key not in allowed:
                continue
            if self._is_empty(value):
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self.merge_fields(merged[key], value)
            else:
                merged[key] = value
        return merged

    def merge_state(self, state: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        result = deepcopy(state or {})
        result["known_fields"] = self.merge_fields(
            result.get("known_fields") or {},
            patch.get("known_fields") or {},
        )
        for key in (
            "goal", "active_flow", "active_entity", "pending_action",
            "last_bot_message", "last_bot_intent", "expected_reply_type",
            "last_user_message",
        ):
            value = patch.get(key)
            if not self._is_empty(value):
                result[key] = value
        if "missing_fields" in patch and patch.get("missing_fields") is not None:
            result["missing_fields"] = list(dict.fromkeys(patch.get("missing_fields") or []))
        return result

    def apply_explicit_change(self, state: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
        patch = {"known_fields": {k: v for k, v in changes.items() if not self._is_empty(v)}}
        return self.merge_state(state, patch)

    @classmethod
    def _is_empty(cls, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}
