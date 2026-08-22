import os

import imageio_ffmpeg
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.models.session import ConversationStep

router = APIRouter(prefix="/debug", tags=["Debug"])


class DebugMessageRequest(BaseModel):
    sender_mobile: str
    message: str


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
