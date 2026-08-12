import os

import imageio_ffmpeg
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/debug", tags=["Debug"])


class DebugMessageRequest(BaseModel):
    sender_mobile: str
    message: str


@router.post("/message")
def debug_message(
    payload: DebugMessageRequest,
    request: Request,
) -> dict:
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
