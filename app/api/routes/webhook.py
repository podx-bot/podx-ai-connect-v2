import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.models.session import ConversationStep
from app.services.webhook_recovery_service import WebhookRecoveryService
from app.whatsapp.payload_parser import (
    extract_audio_messages,
    extract_delivery_statuses,
    extract_location_messages,
    extract_text_messages,
)

router = APIRouter(tags=["WhatsApp"])
logger = logging.getLogger("podx.whatsapp.webhook")


def visible_log(message: str) -> None:
    print(message, flush=True)
    logger.info(message)


def _recover_user(container, sender_mobile: str, kind: str) -> dict:
    result = WebhookRecoveryService.send(
        container.whatsapp_service,
        sender_mobile,
        kind,
    )
    visible_log(
        f"WHATSAPP RECOVERY NOTICE: kind={kind} sender={sender_mobile} "
        f"success={bool(result.get('success'))}"
    )
    return result


def _process_user_text(container, sender_mobile: str, message: str) -> str:
    easy_reply = container.easy_job_command_service.process_text(
        sender_mobile=sender_mobile,
        message=message,
    )
    if easy_reply is not None:
        visible_log(f"EASY JOB COMMAND: sender={sender_mobile} text={message}")
        return easy_reply

    lifecycle_reply = container.job_lifecycle_service.process_text(
        sender_mobile=sender_mobile,
        message=message,
    )
    if lifecycle_reply is not None:
        visible_log(f"JOB LIFECYCLE COMMAND: sender={sender_mobile} text={message}")
        return lifecycle_reply

    insurance_service = getattr(container, "insurance_assistant_service", None)
    if insurance_service is not None and insurance_service.is_insurance_message(message):
        insurance_reply = insurance_service.answer(message)
        visible_log(
            f"INSURANCE ASSISTANT: sender={sender_mobile} "
            f"status={insurance_reply.get('status')} next={insurance_reply.get('next_action')}"
        )
        return insurance_reply["answer"]

    return container.conversation_service.process(
        sender_mobile=sender_mobile,
        message=message,
    )


def _send_spoken_reply(container, sender_mobile: str, reply_text: str) -> dict:
    if not container.settings.voice_reply_enabled:
        return {"success": False, "status": "VOICE_REPLY_DISABLED"}

    synthesis = container.voice_assistant_service.synthesize(reply_text)
    if not synthesis.get("success"):
        visible_log(
            "PODX TTS FAILED: "
            f"sender={sender_mobile} status={synthesis.get('status')} "
            f"error={synthesis.get('error')}"
        )
        return {"success": False, "status": "TTS_FAILED", "synthesis": synthesis}

    conversion = container.audio_codec_service.pcm_to_ogg_opus(
        pcm_bytes=synthesis["content"],
        sample_rate=int(synthesis.get("sample_rate") or 24000),
        channels=int(synthesis.get("channels") or 1),
    )
    if not conversion.get("success"):
        visible_log(
            "PODX VOICE CONVERSION FAILED: "
            f"sender={sender_mobile} status={conversion.get('status')} "
            f"error={conversion.get('error')}"
        )
        return {"success": False, "status": "VOICE_CONVERSION_FAILED", "conversion": conversion}

    send_result = container.whatsapp_service.send_voice_bytes(
        recipient_mobile=sender_mobile,
        audio_bytes=conversion["content"],
        mime_type=conversion.get("mime_type") or "audio/ogg",
        file_name=conversion.get("file_name") or "podx-reply.ogg",
    )
    visible_log(f"PODX VOICE SEND RESULT: sender={sender_mobile} result={send_result}")
    return send_result


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    container = request.app.state.container
    if (
        hub_mode == "subscribe"
        and hub_verify_token == container.settings.whatsapp_webhook_verify_token
        and hub_challenge is not None
    ):
        visible_log("WHATSAPP WEBHOOK VERIFIED")
        return hub_challenge
    visible_log("WHATSAPP WEBHOOK VERIFICATION FAILED")
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    container = request.app.state.container
    try:
        payload = await request.json()
    except Exception as error:
        visible_log(f"WHATSAPP PAYLOAD JSON ERROR: {error}")
        raise HTTPException(status_code=400, detail="Invalid webhook JSON payload.")

    try:
        statuses = extract_delivery_statuses(payload)
        text_messages = extract_text_messages(payload)
        audio_messages = extract_audio_messages(payload)
        location_messages = extract_location_messages(payload)
    except Exception as error:
        visible_log(f"WHATSAPP PARSER ERROR: {type(error).__name__}: {error}")
        return {"status": "parser_error", "error": str(error)}

    visible_log(
        "WHATSAPP INCOMING: "
        f"text={len(text_messages)} audio={len(audio_messages)} "
        f"location={len(location_messages)} status={len(statuses)}"
    )

    if not statuses and not text_messages and not audio_messages and not location_messages:
        visible_log(f"WHATSAPP IGNORED PAYLOAD: object={payload.get('object')}")

    for status in statuses:
        try:
            container.delivery_log_repository.save_status(
                provider_message_id=status.provider_message_id,
                recipient_mobile=status.recipient_mobile,
                status=status.status,
                error_message=status.error_message,
            )
            visible_log(f"WHATSAPP DELIVERY STATUS: id={status.provider_message_id} status={status.status}")
        except Exception as error:
            visible_log(f"WHATSAPP DELIVERY STATUS ERROR: {type(error).__name__}: {error}")

    replies = []

    for incoming in text_messages:
        try:
            visible_log(
                f"WHATSAPP TEXT RECEIVED: sender={incoming.sender_mobile} "
                f"id={incoming.provider_message_id} text={incoming.message_text}"
            )
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(f"WHATSAPP DUPLICATE TEXT SKIPPED: id={incoming.provider_message_id}")
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=incoming.message_text,
            )
            reply_text = _process_user_text(container, incoming.sender_mobile, incoming.message_text)
            visible_log(f"WHATSAPP REPLY CREATED: sender={incoming.sender_mobile} reply={reply_text}")
            send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text,
            )
            visible_log(f"WHATSAPP TEXT SEND RESULT: sender={incoming.sender_mobile} result={send_result}")
            replies.append({
                "message_type": "text",
                "sender_mobile": incoming.sender_mobile,
                "reply": reply_text,
                "send_result": send_result,
            })
        except Exception as error:
            visible_log(f"WHATSAPP TEXT PROCESSING ERROR: {type(error).__name__}: {error}")
            replies.append({
                "message_type": "text",
                "sender_mobile": incoming.sender_mobile,
                "error": str(error),
                "recovery": _recover_user(container, incoming.sender_mobile, "text"),
            })

    for incoming in location_messages:
        try:
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(f"WHATSAPP DUPLICATE LOCATION SKIPPED: id={incoming.provider_message_id}")
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"LOCATION {incoming.latitude},{incoming.longitude}",
            )
            location_reply = container.conversation_service.process_location(
                sender_mobile=incoming.sender_mobile,
                latitude=incoming.latitude,
                longitude=incoming.longitude,
                name=incoming.name,
                address=incoming.address,
            )
            send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=location_reply,
            )
            replies.append({
                "message_type": "location",
                "sender_mobile": incoming.sender_mobile,
                "reply": location_reply,
                "send_result": send_result,
            })
        except Exception as error:
            visible_log(f"WHATSAPP LOCATION PROCESSING ERROR: {type(error).__name__}: {error}")
            replies.append({
                "message_type": "location",
                "sender_mobile": incoming.sender_mobile,
                "error": str(error),
                "recovery": _recover_user(container, incoming.sender_mobile, "location"),
            })

    for incoming in audio_messages:
        try:
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(f"WHATSAPP DUPLICATE AUDIO SKIPPED: id={incoming.provider_message_id}")
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text="[voice message]",
            )
            media_result = container.whatsapp_service.download_media(incoming.media_id)
            if not media_result.get("success"):
                raise RuntimeError(f"WhatsApp audio download failed: {media_result.get('status')}")
            transcription = container.voice_assistant_service.transcribe(
                audio_bytes=media_result["content"],
                mime_type=media_result.get("mime_type") or incoming.mime_type,
            )
            if not transcription.get("success"):
                raise RuntimeError(f"Voice transcription failed: {transcription.get('status')}")
            normalized = container.voice_assistant_service.normalize_spoken_choice(transcription["transcript"])
            reply_text = _process_user_text(container, incoming.sender_mobile, normalized)
            text_send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text,
            )
            voice_send_result = _send_spoken_reply(container, incoming.sender_mobile, reply_text)
            replies.append({
                "message_type": "audio",
                "sender_mobile": incoming.sender_mobile,
                "transcript": normalized,
                "reply": reply_text,
                "text_send_result": text_send_result,
                "voice_send_result": voice_send_result,
            })
        except Exception as error:
            visible_log(f"WHATSAPP AUDIO PROCESSING ERROR: {type(error).__name__}: {error}")
            replies.append({
                "message_type": "audio",
                "sender_mobile": incoming.sender_mobile,
                "error": str(error),
                "recovery": _recover_user(container, incoming.sender_mobile, "audio"),
            })

    return {"status": "processed", "replies": replies}
