import os

import imageio_ffmpeg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.models.session import ConversationStep

router = APIRouter(prefix="/debug", tags=["Debug"])


class DebugMessageRequest(BaseModel):
    sender_mobile: str
    message: str


class DebugLocationRequest(BaseModel):
    sender_mobile: str
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    location_name: str | None = None
    location_address: str | None = None


class DebugMatchActionRequest(BaseModel):
    user_id: str
    request_id: int
    action: str


def _prepare_askodox_app_identity(container, sender_mobile: str) -> None:
    """Make an app-* identity eligible for the universal runtime without WhatsApp onboarding.

    ASKODOX mobile installs use a persistent app-* sender id. The universal brain
    expects a registered identity before it will persist NEED/OFFER records. App
    sessions already own their UI onboarding, so create a lightweight internal
    identity and put its conversation session directly at MAIN_MENU. This keeps
    Flutter on the exact same Universal AI/Deal Brain path as registered WhatsApp
    users while avoiding the legacy phone/name/language registration prompts.
    """
    existing = container.user_repository.find_by_whatsapp_mobile(sender_mobile)
    if not existing or not int(existing.get("registration_complete") or 0):
        container.user_repository.create_or_update_registration(
            whatsapp_mobile=sender_mobile,
            entered_mobile=sender_mobile,
            name="ASKODOX App User",
            language="English",
            area="",
        )

    session = container.session_registry.get(sender_mobile)
    if session.step != ConversationStep.MAIN_MENU:
        session.step = ConversationStep.MAIN_MENU
        session.data.clear()
        container.session_registry.save(sender_mobile)


@router.post("/message")
def debug_message(
    payload: DebugMessageRequest,
    request: Request,
) -> dict:
    container = request.app.state.container
    sender_mobile = payload.sender_mobile.strip()

    # Flutter and WhatsApp now share the same UniversalAwareConversationService:
    # response commands -> product/RAG intelligence -> image text follow-ups ->
    # Gemini UniversalRequestExtractor -> universal demand capture -> matcher ->
    # targeting/notification -> escalation/fallback runtimes. The only app-only
    # behavior is bypassing legacy WhatsApp registration prompts.
    if sender_mobile.lower().startswith("app-"):
        _prepare_askodox_app_identity(container, sender_mobile)

    reply = container.conversation_service.process(
        sender_mobile=sender_mobile,
        message=payload.message,
    )

    return {
        "sender_mobile": payload.sender_mobile,
        "message": payload.message,
        "reply": reply,
    }


@router.post("/location")
def debug_location(
    payload: DebugLocationRequest,
    request: Request,
) -> dict:
    """Merge an ASKODOX app GPS/map pin into the latest pending universal request."""
    container = request.app.state.container
    sender_mobile = payload.sender_mobile.strip()
    if sender_mobile.lower().startswith("app-"):
        _prepare_askodox_app_identity(container, sender_mobile)

    reply = container.universal_live_capture_service.handle_location(
        sender_mobile=sender_mobile,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_name=(payload.location_name or "").strip() or None,
        location_address=(payload.location_address or "").strip() or None,
    )
    if reply is None:
        reply = (
            "📍 Location save అయింది. ప్రస్తుతం location కోసం waitingలో ఉన్న request లేదు. "
            "మీ next requestకి ఈ location nearby matchingలో ఉపయోగిస్తాను."
        )

    return {
        "sender_mobile": payload.sender_mobile,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "reply": reply,
    }


@router.get("/inbox/{user_id}")
def debug_inbox(user_id: str, request: Request) -> dict:
    """Return ASKODOX in-app match cards and interest updates for one app identity."""
    container = request.app.state.container
    app_user = user_id.strip()
    if not app_user.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail="ASKODOX app user id required")

    _prepare_askodox_app_identity(container, app_user)
    db = container.database

    match_rows = db.fetchall(
        """
        SELECT n.request_id,n.requester_user_id,n.target_user_id,n.wave,
               n.distance_km,n.relevance_score,n.status AS notification_status,
               n.created_at,
               d.side,d.domain,d.subject,d.quantity,d.unit,d.price,d.currency,
               d.when_text,d.location_text,d.latitude,d.longitude,d.status AS request_status
        FROM universal_notifications n
        JOIN universal_need_offer_records d ON d.id=n.request_id
        WHERE n.target_user_id=? AND n.status IN ('SENT','INTERESTED')
        ORDER BY n.id DESC
        LIMIT 50
        """,
        (app_user,),
    )

    interest_rows = db.fetchall(
        """
        SELECT i.request_id,i.requester_user_id,i.responder_user_id,
               i.responder_status,i.requester_status,i.qualification_status,
               i.contact_shared,i.created_at,i.updated_at,
               d.side,d.domain,d.subject,d.quantity,d.unit,d.price,d.currency,
               d.when_text,d.location_text,d.status AS request_status
        FROM universal_interests i
        JOIN universal_need_offer_records d ON d.id=i.request_id
        WHERE i.requester_user_id=?
        ORDER BY i.id DESC
        LIMIT 50
        """,
        (app_user,),
    )

    matches = []
    for row in match_rows:
        item = dict(row)
        item["actions"] = ["INTERESTED", "NOT_INTERESTED"]
        item["card_type"] = "MATCH"
        matches.append(item)

    updates = []
    for row in interest_rows:
        item = dict(row)
        item["card_type"] = "INTEREST_UPDATE"
        item["actions"] = ["ACCEPT", "DECLINE"] if item.get("requester_status") == "PENDING" else []
        updates.append(item)

    return {
        "user_id": app_user,
        "channel": "in_app",
        "match_count": len(matches),
        "interest_update_count": len(updates),
        "matches": matches,
        "interest_updates": updates,
    }


@router.post("/match-action")
def debug_match_action(payload: DebugMatchActionRequest, request: Request) -> dict:
    """Handle Interested/Not Interested directly inside ASKODOX without WhatsApp."""
    container = request.app.state.container
    app_user = payload.user_id.strip()
    action = payload.action.strip().upper().replace(" ", "_")
    if not app_user.lower().startswith("app-"):
        raise HTTPException(status_code=400, detail="ASKODOX app user id required")
    if action not in {"INTERESTED", "NOT_INTERESTED"}:
        raise HTTPException(status_code=400, detail="action must be INTERESTED or NOT_INTERESTED")

    _prepare_askodox_app_identity(container, app_user)
    demand = container.universal_demand_repository.get(payload.request_id)
    if not demand or str(demand.get("status") or "").upper() != "ACTIVE":
        raise HTTPException(status_code=404, detail="active match request not found")
    if not container.universal_notification_repository.was_targeted(payload.request_id, app_user):
        raise HTTPException(status_code=403, detail="this match was not targeted to this user")

    if action == "NOT_INTERESTED":
        container.database.execute(
            """
            UPDATE universal_notifications
            SET status='DISMISSED',updated_at=CURRENT_TIMESTAMP
            WHERE request_id=? AND target_user_id=?
            """,
            (payload.request_id, app_user),
        )
        return {
            "status": "DISMISSED",
            "request_id": payload.request_id,
            "user_id": app_user,
            "channel": "in_app",
        }

    result = container.universal_notification_service.register_interest(
        demand,
        app_user,
        None,
    )
    container.database.execute(
        """
        UPDATE universal_notifications
        SET status='INTERESTED',updated_at=CURRENT_TIMESTAMP
        WHERE request_id=? AND target_user_id=?
        """,
        (payload.request_id, app_user),
    )
    return {
        **result,
        "action": "INTERESTED",
        "user_id": app_user,
        "channel": "in_app",
    }


@router.get("/whatsapp-diagnostics")
def whatsapp_diagnostics(request: Request) -> dict:
    """Expose non-secret checkpoints for live WhatsApp delivery diagnosis.

    This endpoint deliberately returns counts/timestamps only. It never exposes
    phone numbers, message text, access tokens, provider IDs, or conversation
    contents, so production reachability can be diagnosed safely.
    """
    container = request.app.state.container
    db = container.database

    def snapshot(table: str) -> dict:
        try:
            row = db.fetchone(
                f"SELECT COUNT(*) AS total, MAX(created_at) AS last_at FROM {table}"
            )
            return {
                "ok": True,
                "total": int(row["total"] or 0) if row else 0,
                "last_at": row["last_at"] if row else None,
            }
        except Exception as error:
            return {
                "ok": False,
                "total": None,
                "last_at": None,
                "error": f"{type(error).__name__}: {error}",
            }

    inbound = snapshot("inbound_messages")
    delivery = snapshot("delivery_statuses")
    turns = snapshot("conversation_os_turns")

    checks = {
        "database_ok": bool(db.health_check()),
        "whatsapp_configured": bool(container.whatsapp_service.is_configured()),
        "conversation_os_attached": bool(
            getattr(container, "conversation_os_runtime_service", None)
        ),
        "inbound_table_ok": bool(inbound.get("ok")),
        "delivery_table_ok": bool(delivery.get("ok")),
        "conversation_turn_table_ok": bool(turns.get("ok")),
    }

    return {
        "status": "READY" if all(checks.values()) else "DEGRADED",
        "checks": checks,
        "checkpoints": {
            "inbound_messages": inbound,
            "delivery_statuses": delivery,
            "conversation_turns": turns,
        },
        "interpretation": {
            "inbound_not_changing": "Meta webhook is not reaching or not being parsed/claimed by PODX.",
            "inbound_changes_turns_do_not": "Webhook arrives but conversation runtime is not completing.",
            "turns_change_delivery_does_not": "PODX creates a reply but outbound Meta delivery needs inspection.",
        },
    }


@router.get("/voice-readiness")
def voice_readiness(request: Request) -> dict:
    """Return non-secret runtime readiness for the Voice V2 outbound pipeline."""
    container = request.app.state.container
    settings = container.settings

    ffmpeg_path = ""
    ffmpeg_available = False
    ffmpeg_error = None
    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_available = bool(ffmpeg_path and os.path.exists(ffmpeg_path))
    except Exception as error:
        ffmpeg_error = f"{type(error).__name__}: {error}"

    checks = {
        "voice_reply_enabled": bool(settings.voice_reply_enabled),
        "gemini_api_key_present": bool(settings.gemini_api_key),
        "tts_model_present": bool(settings.gemini_tts_model),
        "tts_voice_present": bool(settings.gemini_tts_voice),
        "whatsapp_configured": bool(container.whatsapp_service.is_configured()),
        "ffmpeg_available": ffmpeg_available,
    }

    return {
        "status": "READY" if all(checks.values()) else "NOT_READY",
        "checks": checks,
        "tts_model": settings.gemini_tts_model,
        "tts_voice": settings.gemini_tts_voice,
        "voice_reply_max_chars": settings.voice_reply_max_chars,
        "ffmpeg_path_present": bool(ffmpeg_path),
        "ffmpeg_error": ffmpeg_error,
    }
