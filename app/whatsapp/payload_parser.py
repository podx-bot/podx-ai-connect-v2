from typing import Any

from app.models.whatsapp import (
    DeliveryStatus,
    IncomingAudioMessage,
    IncomingImageMessage,
    IncomingLocationMessage,
    IncomingTextMessage,
)


def _message_values(payload: dict[str, Any]):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                yield message


def extract_text_messages(payload: dict[str, Any]) -> list[IncomingTextMessage]:
    results: list[IncomingTextMessage] = []
    for message in _message_values(payload):
        if message.get("type") != "text":
            continue
        sender_mobile = str(message.get("from", "")).strip()
        provider_message_id = str(message.get("id", "")).strip()
        message_text = str(message.get("text", {}).get("body", "")).strip()
        if sender_mobile and provider_message_id and message_text:
            results.append(IncomingTextMessage(provider_message_id, sender_mobile, message_text))
    return results


def extract_audio_messages(payload: dict[str, Any]) -> list[IncomingAudioMessage]:
    results: list[IncomingAudioMessage] = []
    for message in _message_values(payload):
        if message.get("type") != "audio":
            continue
        sender_mobile = str(message.get("from", "")).strip()
        provider_message_id = str(message.get("id", "")).strip()
        audio = message.get("audio", {}) or {}
        media_id = str(audio.get("id", "")).strip()
        mime_type = audio.get("mime_type")
        if sender_mobile and provider_message_id and media_id:
            results.append(IncomingAudioMessage(provider_message_id, sender_mobile, media_id, str(mime_type).strip() if mime_type else None, bool(audio.get("voice", False))))
    return results


def extract_image_messages(payload: dict[str, Any]) -> list[IncomingImageMessage]:
    results: list[IncomingImageMessage] = []
    for message in _message_values(payload):
        if message.get("type") != "image":
            continue
        sender_mobile = str(message.get("from", "")).strip()
        provider_message_id = str(message.get("id", "")).strip()
        image = message.get("image", {}) or {}
        media_id = str(image.get("id", "")).strip()
        mime_type = image.get("mime_type")
        caption = image.get("caption")
        if sender_mobile and provider_message_id and media_id:
            results.append(
                IncomingImageMessage(
                    provider_message_id=provider_message_id,
                    sender_mobile=sender_mobile,
                    media_id=media_id,
                    mime_type=str(mime_type).strip() if mime_type else None,
                    caption=str(caption).strip() if caption else None,
                )
            )
    return results


def extract_location_messages(payload: dict[str, Any]) -> list[IncomingLocationMessage]:
    results: list[IncomingLocationMessage] = []
    for message in _message_values(payload):
        if message.get("type") != "location":
            continue
        sender_mobile = str(message.get("from", "")).strip()
        provider_message_id = str(message.get("id", "")).strip()
        location = message.get("location", {}) or {}
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if not sender_mobile or not provider_message_id or latitude is None or longitude is None:
            continue
        try:
            latitude_value = float(latitude)
            longitude_value = float(longitude)
        except (TypeError, ValueError):
            continue
        if not (-90 <= latitude_value <= 90) or not (-180 <= longitude_value <= 180):
            continue
        name = location.get("name")
        address = location.get("address")
        results.append(IncomingLocationMessage(provider_message_id, sender_mobile, latitude_value, longitude_value, str(name).strip() if name is not None else None, str(address).strip() if address is not None else None))
    return results


def extract_delivery_statuses(payload: dict[str, Any]) -> list[DeliveryStatus]:
    results: list[DeliveryStatus] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for status in value.get("statuses", []):
                errors = status.get("errors", [])
                error_message = str(errors[0]) if errors else None
                results.append(DeliveryStatus(str(status.get("id", "")).strip(), str(status.get("recipient_id")).strip() if status.get("recipient_id") else None, str(status.get("status", "unknown")).strip(), error_message))
    return results
