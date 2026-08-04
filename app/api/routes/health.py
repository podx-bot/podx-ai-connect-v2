from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/")
def home() -> dict:
    return {
        "status": "Running",
        "app": "PODX AI CONNECT V2"
    }


@router.get("/health")
def health(request: Request) -> dict:
    container = request.app.state.container
    return {
        "status": "healthy",
        "database": container.database.health_check(),
        "whatsapp_configured": (
            container.whatsapp_service.is_configured()
        )
    }
