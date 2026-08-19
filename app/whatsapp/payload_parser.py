from typing import Any

from app.models.whatsapp import (
    DeliveryStatus,
    IncomingAudioMessage,
    IncomingDocumentMessage,
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
    results = []
    for message in _message_values(payload):
        message_type = message.get("type")
        text = ""
        if message_type == "text":
            text = str(message.get("text", {}).get("body", "")).strip()
        elif message_type == "interactive":
            interactive = message.get("interactive", {}) or {}
            if interactive.get("type") == "button_reply":
                text = str((interactive.get("button_reply") or {}).get("id", "")).strip()
            elif interactive.get("type") == "list_reply":
                text = str((interactive.get("list_reply") or {}).get("id", "")).strip()
        elif message_type == "button":
            text = str((message.get("button") or {}).get("payload", "")).strip()
        else:
            continue
        sender = str(message.get("from", "")).strip()
        provider_id = str(message.get("id", "")).strip()
        if sender and provider_id and text:
            results.append(IncomingTextMessage(provider_id, sender, text))
    return results


def extract_audio_messages(payload: dict[str, Any]) -> list[IncomingAudioMessage]:
    results = []
    for message in _message_values(payload):
        if message.get("type") != "audio":
            continue
        sender = str(message.get("from", "")).strip()
        provider_id = str(message.get("id", "")).strip()
        audio = message.get("audio", {}) or {}
        media_id = str(audio.get("id", "")).strip()
        mime = audio.get("mime_type")
        if sender and provider_id and media_id:
            results.append(IncomingAudioMessage(provider_id, sender, media_id, str(mime).strip() if mime else None, bool(audio.get("voice", False))))
    return results


def extract_image_messages(payload: dict[str, Any]) -> list[IncomingImageMessage]:
    results = []
    for message in _message_values(payload):
        if message.get("type") != "image":
            continue
        sender = str(message.get("from", "")).strip()
        provider_id = str(message.get("id", "")).strip()
        image = message.get("image", {}) or {}
        media_id = str(image.get("id", "")).strip()
        mime = image.get("mime_type")
        caption = image.get("caption")
        if sender and provider_id and media_id:
            results.append(IncomingImageMessage(provider_message_id=provider_id, sender_mobile=sender, media_id=media_id, mime_type=str(mime).strip() if mime else None, caption=str(caption).strip() if caption else None))
    return results


def extract_document_messages(payload: dict[str, Any]) -> list[IncomingDocumentMessage]:
    results = []
    for message in _message_values(payload):
        if message.get("type") != "document":
            continue
        sender = str(message.get("from", "")).strip()
        provider_id = str(message.get("id", "")).strip()
        document = message.get("document", {}) or {}
        media_id = str(document.get("id", "")).strip()
        mime = document.get("mime_type")
        caption = document.get("caption")
        filename = document.get("filename")
        if sender and provider_id and media_id:
            results.append(IncomingDocumentMessage(provider_message_id=provider_id, sender_mobile=sender, media_id=media_id, mime_type=str(mime).strip() if mime else None, caption=str(caption).strip() if caption else None, filename=str(filename).strip() if filename else None))
    return results


def extract_location_messages(payload: dict[str, Any]) -> list[IncomingLocationMessage]:
    results = []
    for message in _message_values(payload):
        if message.get("type") != "location":
            continue
        sender = str(message.get("from", "")).strip()
        provider_id = str(message.get("id", "")).strip()
        location = message.get("location", {}) or {}
        lat = location.get("latitude")
        lon = location.get("longitude")
        if not sender or not provider_id or lat is None or lon is None:
            continue
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            continue
        name = location.get("name")
        address = location.get("address")
        results.append(IncomingLocationMessage(provider_id, sender, lat, lon, str(name).strip() if name is not None else None, str(address).strip() if address is not None else None))
    return results


def _format_delivery_error(error: Any) -> str | None:
    if not isinstance(error, dict):
        return str(error).strip() if error else None
    code = str(error.get("code") or "").strip()
    title = str(error.get("title") or "").strip()
    message = str(error.get("message") or "").strip()
    data = error.get("error_data") or {}
    details = str(data.get("details") or "").strip() if isinstance(data, dict) else ""
    parts = []
    if code:
        parts.append(f"META_CODE={code}")
    if title:
        parts.append(f"TITLE={title}")
    if message:
        parts.append(f"MESSAGE={message}")
    if details:
        parts.append(f"DETAILS={details}")
    return " | ".join(parts) if parts else str(error)


def extract_delivery_statuses(payload: dict[str, Any]) -> list[DeliveryStatus]:
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for status in change.get("value", {}).get("statuses", []):
                errors = status.get("errors", [])
                error_message = _format_delivery_error(errors[0]) if errors else None
                results.append(DeliveryStatus(str(status.get("id", "")).strip(), str(status.get("recipient_id")).strip() if status.get("recipient_id") else None, str(status.get("status", "unknown")).strip(), error_message))
    return results
