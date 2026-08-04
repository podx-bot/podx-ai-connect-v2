from typing import Any

from app.models.whatsapp import (
    DeliveryStatus,
    IncomingLocationMessage,
    IncomingTextMessage
)


def extract_text_messages(
    payload: dict[str, Any]
) -> list[IncomingTextMessage]:
    results: list[IncomingTextMessage] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue

                sender_mobile = str(
                    message.get("from", "")
                ).strip()
                provider_message_id = str(
                    message.get("id", "")
                ).strip()
                message_text = str(
                    message.get("text", {}).get("body", "")
                ).strip()

                if (
                    sender_mobile
                    and provider_message_id
                    and message_text
                ):
                    results.append(
                        IncomingTextMessage(
                            provider_message_id=(
                                provider_message_id
                            ),
                            sender_mobile=sender_mobile,
                            message_text=message_text
                        )
                    )

    return results


def extract_location_messages(
    payload: dict[str, Any]
) -> list[IncomingLocationMessage]:
    results: list[IncomingLocationMessage] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for message in value.get("messages", []):
                if message.get("type") != "location":
                    continue

                sender_mobile = str(
                    message.get("from", "")
                ).strip()
                provider_message_id = str(
                    message.get("id", "")
                ).strip()
                location = message.get("location", {})

                latitude = location.get("latitude")
                longitude = location.get("longitude")

                if (
                    not sender_mobile
                    or not provider_message_id
                    or latitude is None
                    or longitude is None
                ):
                    continue

                try:
                    latitude_value = float(latitude)
                    longitude_value = float(longitude)
                except (TypeError, ValueError):
                    continue

                if not (-90 <= latitude_value <= 90):
                    continue

                if not (-180 <= longitude_value <= 180):
                    continue

                name = location.get("name")
                address = location.get("address")

                results.append(
                    IncomingLocationMessage(
                        provider_message_id=(
                            provider_message_id
                        ),
                        sender_mobile=sender_mobile,
                        latitude=latitude_value,
                        longitude=longitude_value,
                        name=(
                            str(name).strip()
                            if name is not None
                            else None
                        ),
                        address=(
                            str(address).strip()
                            if address is not None
                            else None
                        )
                    )
                )

    return results


def extract_delivery_statuses(
    payload: dict[str, Any]
) -> list[DeliveryStatus]:
    results: list[DeliveryStatus] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for status in value.get("statuses", []):
                error_message = None
                errors = status.get("errors", [])

                if errors:
                    error_message = str(errors[0])

                results.append(
                    DeliveryStatus(
                        provider_message_id=str(
                            status.get("id", "")
                        ).strip(),
                        recipient_mobile=(
                            str(status.get("recipient_id")).strip()
                            if status.get("recipient_id")
                            else None
                        ),
                        status=str(
                            status.get("status", "unknown")
                        ).strip(),
                        error_message=error_message
                    )
                )

    return results
