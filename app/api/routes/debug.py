import os
import re

import imageio_ffmpeg
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["Debug"])


class DebugMessageRequest(BaseModel):
    sender_mobile: str
    message: str


def _extract_budget(message: str) -> int | None:
    match = re.search(
        r"(?:₹|rs\.?|inr|under|below|budget(?:\s+is)?|లోపు|కింద)\s*[:₹-]?\s*(\d[\d,]*)",
        message,
        flags=re.IGNORECASE,
    )
    if match is None:
        numbers = re.findall(r"\b\d[\d,]{2,}\b", message)
        if not numbers:
            return None
        raw = numbers[-1]
    else:
        raw = match.group(1)

    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return None


def _detect_buy_item(message: str) -> str | None:
    text = message.lower()
    aliases = (
        (
            "mobile phone",
            ("mobile phone", "smartphone", "mobile", "phone", "మొబైల్", "ఫోన్"),
        ),
        ("laptop", ("laptop", "ల్యాప్‌టాప్")),
        ("tv", ("television", "smart tv", " tv", "టీవీ")),
        ("refrigerator", ("refrigerator", "fridge", "ఫ్రిజ్")),
        ("washing machine", ("washing machine", "వాషింగ్ మెషిన్")),
    )
    for canonical, terms in aliases:
        if any(term in text for term in terms):
            return canonical
    return None


def _process_askodox_app_message(message: str) -> str:
    """Handle Flutter app requests without entering WhatsApp onboarding state."""
    clean = message.strip()
    item = _detect_buy_item(clean)
    budget = _extract_budget(clean)

    if item:
        budget_text = f"₹{budget:,}" if budget is not None else "not specified"
        return (
            "✅ ASKODOX understood your request.\n\n"
            "Intent: Buy\n"
            f"Item: {item}\n"
            f"Budget: {budget_text}\n\n"
            "Your requirement is ready for local seller matching. "
            "Share or confirm your area/location so ASKODOX can continue "
            "with real nearby stock and prices."
        )

    lower = clean.lower()
    if any(term in lower for term in ("sell", "అమ్మ", "విక్రయ")):
        return (
            "✅ ASKODOX understood that you want to sell something. "
            "Tell me the item, quantity, expected price, condition/quality and location."
        )

    if any(term in lower for term in ("job", "work", "పని", "ఉద్యోగ")):
        return (
            "✅ ASKODOX understood that you need work. "
            "Tell me the work type, location, availability and experience."
        )

    if any(term in lower for term in ("service", "plumber", "electrician", "సర్వీస్")):
        return (
            "✅ ASKODOX understood that you need a service. "
            "Tell me the service type, location and preferred time."
        )

    return (
        "ASKODOX is ready. Tell me what you want to buy, sell, find, book, "
        "or get done. I will capture the requirement and ask only for missing details."
    )


@router.post("/message")
def debug_message(
    payload: DebugMessageRequest,
    request: Request,
) -> dict:
    # Flutter ASKODOX sessions deliberately use an app-* sender ID. They already
    # own onboarding/profile state on-device, so they must not be routed through
    # the legacy WhatsApp language/name/area registration state machine.
    if payload.sender_mobile.strip().lower().startswith("app-"):
        reply = _process_askodox_app_message(payload.message)
    else:
        container = request.app.state.container
        reply = container.conversation_service.process(
            sender_mobile=payload.sender_mobile,
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
