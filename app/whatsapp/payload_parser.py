from typing import Any

from app.models.whatsapp import (
    DeliveryStatus,
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
