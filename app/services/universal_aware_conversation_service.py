"""Thin live adapter for Universal Flow responses and natural requirement capture."""

from __future__ import annotations


class UniversalAwareConversationService:
    def __init__(self, response_commands, base_conversation, live_capture=None) -> None:
        self.response_commands = response_commands
        self.live_capture = live_capture
        self.base_conversation = base_conversation

    def process(self, sender_mobile: str, message: str) -> str:
        response_reply = self.response_commands.process_text(
            sender_mobile=sender_mobile,
            message=message,
        )
        if response_reply is not None:
            return response_reply

        if self.live_capture is not None:
            capture_reply = self.live_capture.process_text(
                sender_mobile=sender_mobile,
                message=message,
            )
            if capture_reply is not None:
                return capture_reply

        return self.base_conversation.process(
            sender_mobile=sender_mobile,
            message=message,
        )
