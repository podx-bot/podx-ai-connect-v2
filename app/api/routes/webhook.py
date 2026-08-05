import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.models.session import ConversationStep
from app.whatsapp.payload_parser import (
    extract_delivery_statuses,
    extract_location_messages,
    extract_text_messages
)

router = APIRouter(tags=["WhatsApp"])
logger = logging.getLogger("podx.whatsapp.webhook")


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
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
        logger.info("WHATSAPP WEBHOOK VERIFIED")
        return hub_challenge

    logger.warning("WHATSAPP WEBHOOK VERIFICATION FAILED")
    raise HTTPException(
        status_code=403,
        detail="Webhook verification failed."
    )


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    container = request.app.state.container

    try:
        payload = await request.json()
    except Exception:
        logger.exception("WHATSAPP PAYLOAD JSON ERROR")
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook JSON payload."
        )

    statuses = extract_delivery_statuses(payload)
    text_messages = extract_text_messages(payload)
    location_messages = extract_location_messages(payload)

    logger.info(
        "WHATSAPP INCOMING: text=%s location=%s status=%s",
        len(text_messages),
        len(location_messages),
        len(statuses)
    )

    for status in statuses:
        container.delivery_log_repository.save_status(
            provider_message_id=status.provider_message_id,
            recipient_mobile=status.recipient_mobile,
            status=status.status,
            error_message=status.error_message
        )

    replies = []

    for incoming in text_messages:
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
        logger.info(
            "WHATSAPP TEXT SEND RESULT: sender=%s result=%s",
            incoming.sender_mobile,
            send_result
        )
        replies.append({
            "message_type": "text",
            "sender_mobile": incoming.sender_mobile,
            "reply": reply_text,
            "send_result": send_result
        })

    for incoming in location_messages:
        if container.inbound_message_repository.exists(
            incoming.provider_message_id
        ):
            continue

        container.inbound_message_repository.save(
            provider_message_id=incoming.provider_message_id,
            sender_mobile=incoming.sender_mobile,
            message_text=(
                f"LOCATION:{incoming.latitude:.7f},"
                f"{incoming.longitude:.7f}"
            )
        )

        container.user_repository.save_location(
            whatsapp_mobile=incoming.sender_mobile,
            latitude=incoming.latitude,
            longitude=incoming.longitude,
            location_name=incoming.name,
            location_address=incoming.address
        )

        session = container.session_registry.get(
            incoming.sender_mobile
        )

        if session.step == ConversationStep.WORKER_LOCATION:
            container.user_repository.complete_worker_registration(
                incoming.sender_mobile
            )
            session.step = ConversationStep.MAIN_MENU
            reply_text = (
                "🎉 Worker Registration పూర్తైంది!\n\n"
                f"పని: {session.data.get('category')}\n"
                f"Experience: {session.data.get('experience')}\n"
                f"Availability: {session.data.get('availability')}\n"
                "📍 Location కూడా save అయింది.\n\n"
                "ఇప్పటి నుండి మీకు దగ్గరలో వచ్చే Jobs "
                "WhatsAppలో పంపబడతాయి."
            )
        else:
            reply_text = (
                "✅ మీ location విజయవంతంగా save అయింది.\n"
                f"📍 Latitude: {incoming.latitude:.6f}\n"
                f"📍 Longitude: {incoming.longitude:.6f}\n\n"
                "Nearby jobs మరియు workers matching కోసం "
                "ఈ location ఉపయోగిస్తాం."
            )

        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text
        )
        logger.info(
            "WHATSAPP LOCATION SEND RESULT: sender=%s result=%s",
            incoming.sender_mobile,
            send_result
        )
        replies.append({
            "message_type": "location",
            "sender_mobile": incoming.sender_mobile,
            "latitude": incoming.latitude,
            "longitude": incoming.longitude,
            "reply": reply_text,
            "send_result": send_result
        })

    return {
        "status": "processed",
        "incoming_text_count": len(text_messages),
        "incoming_location_count": len(location_messages),
        "delivery_status_count": len(statuses),
        "replies": replies
    }
