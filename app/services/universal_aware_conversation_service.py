"""Thin live adapter that gives Universal Flow response commands precedence.

Keeping this wrapper separate avoids invasive webhook changes while allowing both
text and transcribed voice messages to use the same response path.
"""

from __future__ import annotations


class UniversalAwareConversationService:
    def __init__(self, response_commands, base_conversation) -> None:
        self.response_commands = response_commands
        self.base_conversation = base_conversation

    def process(self, sender_mobile: str, message: str) -> str:
        universal_reply = self.response_commands.process_text(
            sender_mobile=sender_mobile,
            message=message,
        )
        if universal_reply is not None:
            return universal_reply
        return self.base_conversation.process(
            sender_mobile=sender_mobile,
            message=message,
        )
