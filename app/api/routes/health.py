from fastapi import APIRouter, Request

from app.services.runtime_readiness_service import RuntimeReadinessService

router = APIRouter(tags=["Health"])


def _readiness_payload(settings, database_ok: bool) -> dict:
    readiness = RuntimeReadinessService(settings).check()
    live_test_ready = bool(database_ok and readiness.whatsapp_ready and readiness.webhook_ready)
    return {
        "status": "ready" if live_test_ready else "degraded",
        "live_test_ready": live_test_ready,
        "database_ready": bool(database_ok),
        "critical": {
            "whatsapp_send": readiness.whatsapp_ready,
            "webhook_verify": readiness.webhook_ready,
        },
        "optional": {
            "voice_stt": readiness.voice_stt_ready,
            "voice_tts": readiness.voice_tts_ready,
            "image_ai": readiness.image_ai_ready,
            "maps": readiness.maps_ready,
        },
        "warnings": list(readiness.warnings),
        "payment_policy": {
            "podx_platform_charge": 0,
            "gateway_required_for_testing": False,
        },
    }


@router.get("/")
def home() -> dict:
    return {
        "status": "Running",
        "app": "PODX AI CONNECT V2",
    }


@router.get("/health")
def health(request: Request) -> dict:
    container = request.app.state.container
    return {
        "status": "healthy",
        "database": container.database.health_check(),
        "whatsapp_configured": container.whatsapp_service.is_configured(),
    }


@router.get("/readiness")
def readiness(request: Request) -> dict:
    """Safe pre-live-test readiness summary. Never returns API keys or tokens."""
    container = request.app.state.container
    try:
        database_ok = bool(container.database.health_check())
    except Exception:
        database_ok = False
    return _readiness_payload(container.settings, database_ok)
