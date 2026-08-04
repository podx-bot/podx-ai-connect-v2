import threading

from app.models.session import ConversationSession


class SessionRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, ConversationSession] = {}

    def get(self, sender_mobile: str) -> ConversationSession:
        with self._lock:
            if sender_mobile not in self._sessions:
                self._sessions[sender_mobile] = (
                    ConversationSession()
                )
            return self._sessions[sender_mobile]

    def reset(self, sender_mobile: str) -> None:
        with self._lock:
            self._sessions[sender_mobile] = (
                ConversationSession()
            )
