import logging
import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.routes.webhook import (
    _process_user_text,
    _send_spoken_reply,
    receive_webhook as legacy_receive_webhook,
    visible_log,
)
from app.whatsapp.payload_parser import (
    extract_audio_messages,
    extract_delivery_statuses,
    extract_document_messages,
    extract_image_messages,
    extract_location_messages,
    extract_text_messages,
)

router = APIRouter(tags=["WhatsApp"])
logger = logging.getLogger("podx.whatsapp.fast_webhook")

VOICE_ACK_TEXT = "🎙️ మీ voice అందింది. అర్థం చేసుకుంటున్నాను..."
IMAGE_ACK_TEXT = "📷 మీ photo అందింది. అర్థం చేసుకుంటున్నాను..."
DOCUMENT_ACK_TEXT = "📄 మీ document అందింది. అర్థం చేసుకుంటున్నాను..."


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _process_audio_background(container, incoming) -> None:
    total_started = time.perf_counter()
    request_id = getattr(incoming, "provider_message_id", "unknown")
    transcript = None
    try:
        stage_started = time.perf_counter()
        media_result = container.whatsapp_service.download_media(incoming.media_id)
        visible_log(
            f"VOICE LATENCY: id={request_id} stage=media_download ms={_elapsed_ms(stage_started)} success={bool(media_result.get('success'))}"
        )
        if not media_result.get("success"):
            reply_text = "🎙️ మీ voice message తీసుకోలేకపోయాను. దయచేసి చిన్న voice note మళ్లీ పంపండి లేదా textలో పంపండి."
        else:
            stage_started = time.perf_counter()
            transcription = container.voice_assistant_service.transcribe(
                audio_bytes=media_result["content"],
                mime_type=media_result.get("mime_type") or incoming.mime_type,
            )
            visible_log(
                f"VOICE LATENCY: id={request_id} stage=stt ms={_elapsed_ms(stage_started)} success={bool(transcription.get('success'))} path={transcription.get('transcription_path') or 'unknown'} status={transcription.get('status')}"
            )
            if not transcription.get("success"):
                reply_text = "🎙️ మీ మాట స్పష్టంగా అర్థం కాలేదు. దయచేసి మళ్లీ చిన్నగా చెప్పండి లేదా textలో పంపండి."
            else:
                transcript = container.voice_assistant_service.normalize_spoken_choice(transcription["transcript"])
                visible_log(f"VOICE TRANSCRIPT: sender={incoming.sender_mobile} transcript={transcript}")
                stage_started = time.perf_counter()
                reply_text = _process_user_text(container, incoming.sender_mobile, transcript)
                visible_log(f"VOICE LATENCY: id={request_id} stage=conversation ms={_elapsed_ms(stage_started)}")

        stage_started = time.perf_counter()
        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text,
        )
        visible_log(
            f"VOICE LATENCY: id={request_id} stage=text_send ms={_elapsed_ms(stage_started)} success={bool(send_result.get('success'))} total_to_text_ms={_elapsed_ms(total_started)}"
        )
        if transcript is not None:
            stage_started = time.perf_counter()
            _send_spoken_reply(container, incoming.sender_mobile, reply_text)
            visible_log(
                f"VOICE LATENCY: id={request_id} stage=tts_send ms={_elapsed_ms(stage_started)} total_ms={_elapsed_ms(total_started)}"
            )
    except Exception as error:
        visible_log(f"WHATSAPP BACKGROUND AUDIO ERROR: {type(error).__name__}: {error}")


def _process_image_background(container, incoming) -> None:
    total_started = time.perf_counter()
    request_id = getattr(incoming, "provider_message_id", "unknown")
    try:
        stage_started = time.perf_counter()
        media_result = container.whatsapp_service.download_media(incoming.media_id)
        visible_log(
            f"IMAGE LATENCY: id={request_id} stage=media_download ms={_elapsed_ms(stage_started)} success={bool(media_result.get('success'))}"
        )
        if not media_result.get("success"):
            reply_text = "📷 Photo download కాలేదు. దయచేసి image మళ్లీ పంపండి."
        else:
            content = media_result.get("content") or b""
            if len(content) > 12 * 1024 * 1024:
                reply_text = "📷 Photo size చాలా పెద్దగా ఉంది. చిన్న/compressed photo లేదా screenshot పంపండి."
            else:
                stage_started = time.perf_counter()
                reply_text = container.catering_menu_ai_service.process_media(
                    sender_mobile=incoming.sender_mobile,
                    content=content,
                    mime_type=media_result.get("mime_type") or incoming.mime_type or "image/jpeg",
                    media_ref=incoming.media_id,
                    caption=incoming.caption,
                )
                if reply_text is None:
                    reply_text = container.universal_image_service.process_image(
                        sender_mobile=incoming.sender_mobile,
                        image_bytes=content,
                        mime_type=media_result.get("mime_type") or incoming.mime_type,
                        media_ref=incoming.media_id,
                        caption=incoming.caption,
                    )
                visible_log(
                    f"IMAGE LATENCY: id={request_id} stage=ai_match ms={_elapsed_ms(stage_started)}"
                )
        stage_started = time.perf_counter()
        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text,
        )
        visible_log(
            f"IMAGE LATENCY: id={request_id} stage=text_send ms={_elapsed_ms(stage_started)} success={bool(send_result.get('success'))} total_ms={_elapsed_ms(total_started)}"
        )
    except Exception as error:
        visible_log(f"WHATSAPP BACKGROUND IMAGE ERROR: {type(error).__name__}: {error}")


def _process_document_background(container, incoming) -> None:
    total_started = time.perf_counter()
    request_id = getattr(incoming, "provider_message_id", "unknown")
    try:
        stage_started = time.perf_counter()
        media_result = container.whatsapp_service.download_media(incoming.media_id)
        visible_log(
            f"DOCUMENT LATENCY: id={request_id} stage=media_download ms={_elapsed_ms(stage_started)} success={bool(media_result.get('success'))}"
        )
        if not media_result.get("success"):
            reply_text = "📄 Document download కాలేదు. దయచేసి మళ్లీ పంపండి."
        else:
            content = media_result.get("content") or b""
            if len(content) > 16 * 1024 * 1024:
                reply_text = "📄 Document size చాలా పెద్దగా ఉంది. చిన్న PDF/menu file పంపండి."
            else:
                mime_type = media_result.get("mime_type") or incoming.mime_type or "application/pdf"
                reply_text = container.catering_menu_ai_service.process_media(
                    sender_mobile=incoming.sender_mobile,
                    content=content,
                    mime_type=mime_type,
                    media_ref=incoming.media_id,
                    caption=incoming.caption,
                    filename=incoming.filename,
                )
                if reply_text is None:
                    reply_text = "📄 ప్రస్తుతం document AI intake Catering menu/price-list కోసం readyగా ఉంది. Caterer profile ON చేసి లేదా captionలో CMENU అని పంపండి."
        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text,
        )
        visible_log(
            f"DOCUMENT LATENCY: id={request_id} stage=text_send success={bool(send_result.get('success'))} total_ms={_elapsed_ms(total_started)}"
        )
    except Exception as error:
        visible_log(f"WHATSAPP BACKGROUND DOCUMENT ERROR: {type(error).__name__}: {error}")


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    container = request.app.state.container
    if hub_mode == "subscribe" and hub_verify_token == container.settings.whatsapp_webhook_verify_token and hub_challenge is not None:
        visible_log("WHATSAPP WEBHOOK VERIFIED")
        return hub_challenge
    visible_log("WHATSAPP WEBHOOK VERIFICATION FAILED")
    raise HTTPException(status_code=403, detail="Webhook verification failed.")


@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """Fast-path voice/image/document events; preserve proven legacy path for other events."""
    container = request.app.state.container
    try:
        payload = await request.json()
        audio_messages = extract_audio_messages(payload)
        image_messages = extract_image_messages(payload)
        document_messages = extract_document_messages(payload)
        text_messages = extract_text_messages(payload)
        location_messages = extract_location_messages(payload)
        statuses = extract_delivery_statuses(payload)
    except Exception as error:
        visible_log(f"WHATSAPP FAST PARSER ERROR: {type(error).__name__}: {error}")
        return await legacy_receive_webhook(request)

    if (not audio_messages and not image_messages and not document_messages) or text_messages or location_messages or statuses:
        return await legacy_receive_webhook(request)

    accepted_audio = 0
    accepted_images = 0
    accepted_documents = 0

    for incoming in audio_messages:
        try:
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"AUDIO:{incoming.media_id}",
            )
            container.whatsapp_service.send_text_message(incoming.sender_mobile, VOICE_ACK_TEXT)
            background_tasks.add_task(_process_audio_background, container, incoming)
            accepted_audio += 1
        except Exception as error:
            visible_log(f"WHATSAPP FAST AUDIO ACCEPT ERROR: {type(error).__name__}: {error}")

    for incoming in image_messages:
        try:
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"IMAGE:{incoming.media_id}",
            )
            container.whatsapp_service.send_text_message(incoming.sender_mobile, IMAGE_ACK_TEXT)
            background_tasks.add_task(_process_image_background, container, incoming)
            accepted_images += 1
        except Exception as error:
            visible_log(f"WHATSAPP FAST IMAGE ACCEPT ERROR: {type(error).__name__}: {error}")

    for incoming in document_messages:
        try:
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"DOCUMENT:{incoming.media_id}",
            )
            container.whatsapp_service.send_text_message(incoming.sender_mobile, DOCUMENT_ACK_TEXT)
            background_tasks.add_task(_process_document_background, container, incoming)
            accepted_documents += 1
        except Exception as error:
            visible_log(f"WHATSAPP FAST DOCUMENT ACCEPT ERROR: {type(error).__name__}: {error}")

    return {
        "status": "accepted",
        "incoming_audio_count": len(audio_messages),
        "background_audio_count": accepted_audio,
        "incoming_image_count": len(image_messages),
        "background_image_count": accepted_images,
        "incoming_document_count": len(document_messages),
        "background_document_count": accepted_documents,
    }
