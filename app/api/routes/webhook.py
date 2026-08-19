import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.models.session import ConversationStep
from app.services.insurance_whatsapp_router import InsuranceWhatsAppRouter
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

    insurance_router = getattr(container, "insurance_whatsapp_router", None)
    if insurance_router is None:
        insurance_router = InsuranceWhatsAppRouter()
    insurance_reply = insurance_router.process_text(message)
    if insurance_reply is not None:
        visible_log(f"INSURANCE COMMAND: sender={sender_mobile} text={message}")
        return insurance_reply

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
            _recover_user(container, incoming.sender_mobile, "text")

    for incoming in audio_messages:
        try:
            visible_log(
                f"WHATSAPP AUDIO RECEIVED: sender={incoming.sender_mobile} "
                f"id={incoming.provider_message_id} media_id={incoming.media_id} "
                f"mime={incoming.mime_type} voice={incoming.is_voice}"
            )
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(f"WHATSAPP DUPLICATE AUDIO SKIPPED: id={incoming.provider_message_id}")
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"AUDIO:{incoming.media_id}",
            )
            media_result = container.whatsapp_service.download_media(incoming.media_id)
            if not media_result.get("success"):
                visible_log(f"WHATSAPP AUDIO DOWNLOAD FAILED: sender={incoming.sender_mobile} result={media_result}")
                reply_text = "🎙️ మీ voice message తీసుకోలేకపోయాను. దయచేసి చిన్న voice note మళ్లీ పంపండి లేదా textలో పంపండి."
                transcript = None
            else:
                transcription = container.voice_assistant_service.transcribe(
                    audio_bytes=media_result["content"],
                    mime_type=media_result.get("mime_type") or incoming.mime_type,
                )
                if not transcription.get("success"):
                    visible_log(
                        "GEMINI VOICE TRANSCRIPTION FAILED: "
                        f"sender={incoming.sender_mobile} status={transcription.get('status')} "
                        f"http={transcription.get('http_status')}"
                    )
                    reply_text = "🎙️ మీ మాట స్పష్టంగా అర్థం కాలేదు. దయచేసి మళ్లీ చిన్నగా చెప్పండి లేదా textలో పంపండి."
                    transcript = None
                else:
                    transcript = container.voice_assistant_service.normalize_spoken_choice(transcription["transcript"])
                    visible_log(f"GEMINI VOICE TRANSCRIPT: sender={incoming.sender_mobile} transcript={transcript}")
                    reply_text = _process_user_text(container, incoming.sender_mobile, transcript)

            send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text,
            )
            visible_log(f"WHATSAPP AUDIO TEXT REPLY RESULT: sender={incoming.sender_mobile} result={send_result}")
            voice_send_result = None
            if transcript is not None:
                voice_send_result = _send_spoken_reply(container, incoming.sender_mobile, reply_text)
            replies.append({
                "message_type": "audio",
                "sender_mobile": incoming.sender_mobile,
                "transcript": transcript,
                "reply": reply_text,
                "send_result": send_result,
                "voice_send_result": voice_send_result,
            })
        except Exception as error:
            visible_log(f"WHATSAPP AUDIO PROCESSING ERROR: {type(error).__name__}: {error}")
            _recover_user(container, incoming.sender_mobile, "audio")

    for incoming in location_messages:
        try:
            visible_log(
                f"WHATSAPP LOCATION RECEIVED: sender={incoming.sender_mobile} "
                f"latitude={incoming.latitude} longitude={incoming.longitude}"
            )
            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(f"WHATSAPP DUPLICATE LOCATION SKIPPED: id={incoming.provider_message_id}")
                continue
            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=f"LOCATION:{incoming.latitude:.7f},{incoming.longitude:.7f}",
            )

            session = container.session_registry.get(incoming.sender_mobile)
            if session.step == ConversationStep.WORKER_LOCATION:
                worker_category = session.data.get("category")
                worker_experience = session.data.get("experience")
                worker_availability = session.data.get("availability")
                container.user_repository.save_location(
                    whatsapp_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                    location_name=incoming.name,
                    location_address=incoming.address,
                )
                container.user_repository.complete_worker_registration(incoming.sender_mobile)
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                container.session_registry.save(incoming.sender_mobile)
                reply_text = (
                    "🎉 Worker Registration పూర్తైంది!\n\n"
                    f"పని: {worker_category}\nExperience: {worker_experience}\n"
                    f"Availability: {worker_availability}\n📍 Location కూడా save అయింది.\n\n"
                    "ఇప్పటి నుండి మీకు దగ్గరలో వచ్చే Jobs WhatsAppలో పంపబడతాయి."
                )
            elif session.step == ConversationStep.EMPLOYER_LOCATION:
                job = container.user_repository.save_employer_job_location(
                    whatsapp_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                    location_name=incoming.name,
                    location_address=incoming.address,
                )
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                container.session_registry.save(incoming.sender_mobile)
                if job is None:
                    visible_log(f"JOB MATCHING SKIPPED: sender={incoming.sender_mobile} reason=no_draft_job")
                    reply_text = "⚠️ Job details దొరకలేదు. Hi పంపి Employer workflowను మళ్లీ ప్రారంభించండి."
                else:
                    match_result = container.job_matching_service.match_and_notify(job)
                    visible_log(
                        "JOB MATCHING RESULT: "
                        f"job_id={job['id']} service={job['service']} "
                        f"candidates={match_result['candidate_count']} matched={match_result['matched_count']} "
                        f"notified={match_result['notified_count']} skipped_self={match_result['skipped_self_count']}"
                    )
                    reply_text = (
                        "✅ మీ Job Location save అయింది.\n\n"
                        f"Job ID: #{job['id']}\nపని: {job['service']}\n"
                        f"Requirement: {job['requirement']}\nWorkers required: {job.get('required_workers') or 1}\n"
                        f"📍 Nearby matches: {match_result['matched_count']}\n"
                        f"🔔 Notifications sent: {match_result['notified_count']}\n\n"
                        f"Live status చూడడానికి: STATUS {job['id']}"
                    )
            else:
                container.user_repository.save_location(
                    whatsapp_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                    location_name=incoming.name,
                    location_address=incoming.address,
                )
                tracking_reply = container.job_lifecycle_service.handle_location(
                    worker_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                )
                if tracking_reply is not None:
                    visible_log(
                        f"JOB TRACKING LOCATION: worker={incoming.sender_mobile} "
                        f"latitude={incoming.latitude} longitude={incoming.longitude}"
                    )
                    reply_text = tracking_reply
                else:
                    reply_text = (
                        "✅ మీ location విజయవంతంగా save అయింది.\n"
                        f"📍 Latitude: {incoming.latitude:.6f}\n"
                        f"📍 Longitude: {incoming.longitude:.6f}\n\n"
                        "Nearby jobs మరియు workers matching కోసం ఈ location ఉపయోగిస్తాం."
                    )

            send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text,
            )
            replies.append({
                "message_type": "location",
                "sender_mobile": incoming.sender_mobile,
                "reply": reply_text,
                "send_result": send_result,
            })
        except Exception as error:
            visible_log(f"WHATSAPP LOCATION PROCESSING ERROR: {type(error).__name__}: {error}")
            _recover_user(container, incoming.sender_mobile, "location")

    return {"status": "received", "replies": replies}
