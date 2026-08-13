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
    extract_location_messages,
    extract_text_messages,
)

router = APIRouter(tags=["WhatsApp"])
logger = logging.getLogger("podx.whatsapp.fast_webhook")

VOICE_ACK_TEXT = "🎙️ మీ voice అందింది. అర్థం చేసుకుంటున్నాను..."


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _process_audio_background(container, incoming) -> None:
    """Finish voice processing after the webhook has already acknowledged receipt."""
    total_started = time.perf_counter()
    request_id = incoming.provider_message_id
    transcript = None
    try:
        stage_started = time.perf_counter()
        media_result = container.whatsapp_service.download_media(incoming.media_id)
        visible_log(
            f"VOICE LATENCY: id={request_id} stage=media_download ms={_elapsed_ms(stage_started)} "
            f"success={bool(media_result.get('success'))}"
        )
        if not media_result.get("success"):
            visible_log(
                f"WHATSAPP AUDIO DOWNLOAD FAILED: sender={incoming.sender_mobile} result={media_result}"
            )
            reply_text = (
                "🎙️ మీ voice message తీసుకోలేకపోయాను. "
                "దయచేసి చిన్న voice note మళ్లీ పంపండి లేదా textలో పంపండి."
            )
        else:
            stage_started = time.perf_counter()
            transcription = container.voice_assistant_service.transcribe(
                audio_bytes=media_result["content"],
                mime_type=media_result.get("mime_type") or incoming.mime_type,
            )
            stt_ms = _elapsed_ms(stage_started)
            visible_log(
                f"VOICE LATENCY: id={request_id} stage=stt ms={stt_ms} "
                f"success={bool(transcription.get('success'))} "
                f"path={transcription.get('transcription_path') or 'unknown'} "
                f"status={transcription.get('status')}"
            )
            if not transcription.get("success"):
                visible_log(
                    "VOICE TRANSCRIPTION FAILED: "
                    f"sender={incoming.sender_mobile} status={transcription.get('status')} "
                    f"http={transcription.get('http_status')}"
                )
                reply_text = (
                    "🎙️ మీ మాట స్పష్టంగా అర్థం కాలేదు. "
                    "దయచేసి మళ్లీ చిన్నగా చెప్పండి లేదా textలో పంపండి."
                )
            else:
                transcript = container.voice_assistant_service.normalize_spoken_choice(
                    transcription["transcript"]
                )
                visible_log(
                    "VOICE TRANSCRIPT: "
                    f"sender={incoming.sender_mobile} path={transcription.get('transcription_path')} "
                    f"language={transcription.get('language_code')} transcript={transcript}"
                )
                stage_started = time.perf_counter()
                reply_text = _process_user_text(
                    container,
                    incoming.sender_mobile,
                    transcript,
                )
                visible_log(
                    f"VOICE LATENCY: id={request_id} stage=conversation ms={_elapsed_ms(stage_started)}"
                )

        stage_started = time.perf_counter()
        send_result = container.whatsapp_service.send_text_message(
            recipient_mobile=incoming.sender_mobile,
            message=reply_text,
        )
        text_send_ms = _elapsed_ms(stage_started)
        visible_log(
            f"VOICE LATENCY: id={request_id} stage=text_send ms={text_send_ms} "
            f"success={bool(send_result.get('success'))} total_to_text_ms={_elapsed_ms(total_started)}"
        )
        visible_log(
            f"WHATSAPP AUDIO FINAL TEXT RESULT: sender={incoming.sender_mobile} result={send_result}"
        )

        if transcript is not None:
            stage_started = time.perf_counter()
            _send_spoken_reply(
                container,
                incoming.sender_mobile,
                reply_text,
            )
            visible_log(
                f"VOICE LATENCY: id={request_id} stage=tts_send ms={_elapsed_ms(stage_started)} "
                f"total_ms={_elapsed_ms(total_started)}"
            )
    except Exception as error:
        visible_log(
            f"WHATSAPP BACKGROUND AUDIO ERROR: {type(error).__name__}: {error}"
        )
        visible_log(
            f"VOICE LATENCY: id={request_id} stage=background_error total_ms={_elapsed_ms(total_started)}"
        )


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
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Fast-path voice events; preserve the proven legacy path for other events."""
    container = request.app.state.container

    try:
        payload = await request.json()
        audio_messages = extract_audio_messages(payload)
        text_messages = extract_text_messages(payload)
        location_messages = extract_location_messages(payload)
        statuses = extract_delivery_statuses(payload)
    except Exception as error:
        visible_log(f"WHATSAPP FAST PARSER ERROR: {type(error).__name__}: {error}")
        return await legacy_receive_webhook(request)

    if not audio_messages or text_messages or location_messages or statuses:
        return await legacy_receive_webhook(request)

    accepted = 0
    for incoming in audio_messages:
        try:
            accept_started = time.perf_counter()
            visible_log(
                "WHATSAPP FAST AUDIO RECEIVED: "
                f"sender={incoming.sender_mobile} id={incoming.provider_message_id}"
            )
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(
                    f"WHATSAPP DUPLICATE AUDIO SKIPPED: id={incoming.provider_message_id}"
                )
                continue

            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"AUDIO:{incoming.media_id}",
            )

            ack_stage_started = time.perf_counter()
            ack_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=VOICE_ACK_TEXT,
            )
            visible_log(
                f"VOICE LATENCY: id={incoming.provider_message_id} stage=ack_send "
                f"ms={_elapsed_ms(ack_stage_started)} accepted_ms={_elapsed_ms(accept_started)} "
                f"success={bool(ack_result.get('success'))}"
            )
            visible_log(
                f"WHATSAPP VOICE ACK RESULT: sender={incoming.sender_mobile} result={ack_result}"
            )

            background_tasks.add_task(
                _process_audio_background,
                container,
                incoming,
            )
            accepted += 1
        except Exception as error:
            visible_log(
                f"WHATSAPP FAST AUDIO ACCEPT ERROR: {type(error).__name__}: {error}"
            )

    return {
        "status": "accepted",
        "incoming_audio_count": len(audio_messages),
        "background_audio_count": accepted,
    }
