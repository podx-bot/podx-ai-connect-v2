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


def visible_log(message: str) -> None:
    print(message, flush=True)
    logger.info(message)


@router.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    request: Request,
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge")
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
        location_messages = extract_location_messages(payload)
    except Exception as error:
        visible_log(f"WHATSAPP PARSER ERROR: {type(error).__name__}: {error}")
        return {"status": "parser_error", "error": str(error)}

    visible_log(
        "WHATSAPP INCOMING: "
        f"text={len(text_messages)} "
        f"location={len(location_messages)} "
        f"status={len(statuses)}"
    )

    if not statuses and not text_messages and not location_messages:
        visible_log(f"WHATSAPP IGNORED PAYLOAD: object={payload.get('object')}")

    for status in statuses:
        try:
            container.delivery_log_repository.save_status(
                provider_message_id=status.provider_message_id,
                recipient_mobile=status.recipient_mobile,
                status=status.status,
                error_message=status.error_message
            )
            visible_log(
                "WHATSAPP DELIVERY STATUS: "
                f"id={status.provider_message_id} status={status.status}"
            )
        except Exception as error:
            visible_log(
                "WHATSAPP DELIVERY STATUS ERROR: "
                f"{type(error).__name__}: {error}"
            )

    replies = []

    for incoming in text_messages:
        try:
            visible_log(
                "WHATSAPP TEXT RECEIVED: "
                f"sender={incoming.sender_mobile} "
                f"id={incoming.provider_message_id} "
                f"text={incoming.message_text}"
            )

            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(
                    "WHATSAPP DUPLICATE TEXT SKIPPED: "
                    f"id={incoming.provider_message_id}"
                )
                continue

            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=incoming.message_text
            )

            lifecycle_reply = container.job_lifecycle_service.process_text(
                sender_mobile=incoming.sender_mobile,
                message=incoming.message_text
            )
            if lifecycle_reply is not None:
                reply_text = lifecycle_reply
                visible_log(
                    "JOB LIFECYCLE COMMAND: "
                    f"sender={incoming.sender_mobile} text={incoming.message_text}"
                )
            else:
                reply_text = container.conversation_service.process(
                    sender_mobile=incoming.sender_mobile,
                    message=incoming.message_text
                )

            visible_log(
                "WHATSAPP REPLY CREATED: "
                f"sender={incoming.sender_mobile} reply={reply_text}"
            )

            send_result = container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text
            )
            visible_log(
                "WHATSAPP TEXT SEND RESULT: "
                f"sender={incoming.sender_mobile} result={send_result}"
            )

            replies.append({
                "message_type": "text",
                "sender_mobile": incoming.sender_mobile,
                "reply": reply_text,
                "send_result": send_result
            })
        except Exception as error:
            visible_log(
                "WHATSAPP TEXT PROCESSING ERROR: "
                f"{type(error).__name__}: {error}"
            )

    for incoming in location_messages:
        try:
            visible_log(
                "WHATSAPP LOCATION RECEIVED: "
                f"sender={incoming.sender_mobile} "
                f"latitude={incoming.latitude} longitude={incoming.longitude}"
            )

            if container.inbound_message_repository.exists(incoming.provider_message_id):
                visible_log(
                    "WHATSAPP DUPLICATE LOCATION SKIPPED: "
                    f"id={incoming.provider_message_id}"
                )
                continue

            container.inbound_message_repository.save(
                provider_message_id=incoming.provider_message_id,
                sender_mobile=incoming.sender_mobile,
                message_text=(
                    f"LOCATION:{incoming.latitude:.7f},{incoming.longitude:.7f}"
                )
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
                    location_address=incoming.address
                )
                container.user_repository.complete_worker_registration(
                    incoming.sender_mobile
                )
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                container.session_registry.save(incoming.sender_mobile)

                reply_text = (
                    "🎉 Worker Registration పూర్తైంది!\n\n"
                    f"పని: {worker_category}\n"
                    f"Experience: {worker_experience}\n"
                    f"Availability: {worker_availability}\n"
                    "📍 Location కూడా save అయింది.\n\n"
                    "ఇప్పటి నుండి మీకు దగ్గరలో వచ్చే Jobs WhatsAppలో పంపబడతాయి."
                )

            elif session.step == ConversationStep.EMPLOYER_LOCATION:
                job = container.user_repository.save_employer_job_location(
                    whatsapp_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                    location_name=incoming.name,
                    location_address=incoming.address
                )

                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                container.session_registry.save(incoming.sender_mobile)

                if job is None:
                    visible_log(
                        "JOB MATCHING SKIPPED: "
                        f"sender={incoming.sender_mobile} reason=no_draft_job"
                    )
                    reply_text = (
                        "⚠️ Job details దొరకలేదు. Hi పంపి Employer workflowను మళ్లీ ప్రారంభించండి."
                    )
                else:
                    match_result = container.job_matching_service.match_and_notify(job)
                    visible_log(
                        "JOB MATCHING RESULT: "
                        f"job_id={job['id']} service={job['service']} "
                        f"candidates={match_result['candidate_count']} "
                        f"matched={match_result['matched_count']} "
                        f"notified={match_result['notified_count']} "
                        f"skipped_self={match_result['skipped_self_count']}"
                    )
                    reply_text = (
                        "✅ మీ Job Location save అయింది.\n\n"
                        f"Job ID: #{job['id']}\n"
                        f"పని: {job['service']}\n"
                        f"Requirement: {job['requirement']}\n"
                        f"Workers required: {job.get('required_workers') or 1}\n"
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
                    location_address=incoming.address
                )

                tracking_reply = container.job_lifecycle_service.handle_location(
                    worker_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude
                )
                if tracking_reply is not None:
                    visible_log(
                        "JOB TRACKING LOCATION: "
                        f"worker={incoming.sender_mobile} "
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
                message=reply_text
            )
            visible_log(
                "WHATSAPP LOCATION SEND RESULT: "
                f"sender={incoming.sender_mobile} result={send_result}"
            )

            replies.append({
                "message_type": "location",
                "sender_mobile": incoming.sender_mobile,
                "latitude": incoming.latitude,
                "longitude": incoming.longitude,
                "reply": reply_text,
                "send_result": send_result
            })
        except Exception as error:
            visible_log(
                "WHATSAPP LOCATION PROCESSING ERROR: "
                f"{type(error).__name__}: {error}"
            )

    return {
        "status": "processed",
        "incoming_text_count": len(text_messages),
        "incoming_location_count": len(location_messages),
        "delivery_status_count": len(statuses),
        "replies": replies
    }
