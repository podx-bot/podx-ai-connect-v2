from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IncomingTextMessage:
    provider_message_id: str
    sender_mobile: str
    message_text: str


@dataclass(frozen=True)
class DeliveryStatus:
    provider_message_id: str
    recipient_mobile: Optional[str]
    status: str
    error_message: Optional[str]
