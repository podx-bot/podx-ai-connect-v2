import threading

from app.models.session import ConversationSession
from app.repositories.session_repository import SessionRepository


class SessionRegistry:
    def __init__(self, repository: SessionRepository) -> None:
        self._lock = threading.RLock()
        self._repository = repository
        self._sessions: dict[str, ConversationSession] = {}

    def get(self, sender_mobile: str) -> ConversationSession:
        with self._lock:
            if sender_mobile not in self._sessions:
                self._sessions[sender_mobile] = self._repository.get(
                    sender_mobile
                )
            return self._sessions[sender_mobile]

    def save(self, sender_mobile: str) -> None:
        with self._lock:
            session = self.get(sender_mobile)
            self._repository.save(sender_mobile, session)

    def reset(self, sender_mobile: str) -> None:
        with self._lock:
            self._sessions[sender_mobile] = self._repository.reset(
                sender_mobile
            )
