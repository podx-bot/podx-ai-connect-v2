"""Small wrapper that routes PODX Meet commands before the existing conversation stack."""
from __future__ import annotations


class PodxMeetAwareConversationService:
    def __init__(self, meet_runtime, delegate) -> None:
        self.meet_runtime = meet_runtime
        self.delegate = delegate

    def process(self, sender_mobile: str, message: str) -> str:
        reply = self.meet_runtime.process(sender_mobile, message)
        if reply is not None:
            return reply
        return self.delegate.process(sender_mobile=sender_mobile, message=message)
