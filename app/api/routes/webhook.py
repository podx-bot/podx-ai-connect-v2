from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.whatsapp.payload_parser import (
    extract_delivery_statuses,
    extract_text_messages
)

router = APIRouter(tags=["WhatsApp"])


@router.get(
    "/webhook",
    response_class=PlainTextResponse
)
def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(
        default=None,
        alias="hub.mode"
    ),
    hub_verify_token: Optional[str] = Query(
        default=None,
        alias="hub.verify_token"
    ),
    hub_challenge: Optional[str] = Query(
        default=None,
        alias="hub.challenge"
    )
):
    container = request.app.state.container

    if (
        hub_mode == "subscribe"
        and hub_verify_token
        == container.settings.whatsapp_webhook_verify_token
        and hub_challenge is not None
    ):
        return hub_challenge

    raise HTTPException(
        status_code=403,
        detail="Webhook verification failed."
    )


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    container = request.app.state.container
    payload = await request.json()

    statuses = extract_delivery_statuses(payload)
    messages = extract_text_messages(payload)

    for status in statuses:
        container.delivery_log_repository.save_status(
            provider_message_id=status.provider_message_id,
            recipient_mobile=status.recipient_mobile,
            status=status.status,
            error_message=status.error_message
        )

    replies = []

    for incoming in messages:
        if container.inbound_message_repository.exists(
            incoming.provider_message_id
        ):
            continue

        container.inbound_message_repository.save(
            provider_message_id=incoming.provider_message_id,
            sender_mobile=incoming.sender_mobile,
            message_text=incoming.message_text
        )

        reply_text = container.conversation_service.process(
            sender_mobile=incoming.sender_mobile,
            message=incoming.message_text
        )

        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text
        )

        replies.append(
            {
                "sender_mobile": incoming.sender_mobile,
                "reply": reply_text,
                "send_result": send_result
            }
        )

    return {
        "status": "processed",
        "incoming_message_count": len(messages),
        "delivery_status_count": len(statuses),
        "replies": replies
    }
