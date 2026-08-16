from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IncomingTextMessage:
    provider_message_id: str
    sender_mobile: str
    message_text: str


@dataclass(frozen=True)
class IncomingAudioMessage:
    provider_message_id: str
    sender_mobile: str
    media_id: str
    mime_type: Optional[str]
    is_voice: bool


@dataclass(frozen=True)
class IncomingImageMessage:
    provider_message_id: str
    sender_mobile: str
    media_id: str
    mime_type: Optional[str]
    caption: Optional[str]


@dataclass(frozen=True)
class IncomingDocumentMessage:
    provider_message_id: str
    sender_mobile: str
    media_id: str
    mime_type: Optional[str]
    caption: Optional[str]
    filename: Optional[str]


@dataclass(frozen=True)
class IncomingLocationMessage:
    provider_message_id: str
    sender_mobile: str
    latitude: float
    longitude: float
    name: Optional[str]
    address: Optional[str]


@dataclass(frozen=True)
class DeliveryStatus:
    provider_message_id: str
    recipient_mobile: Optional[str]
    status: str
    error_message: Optional[str]
