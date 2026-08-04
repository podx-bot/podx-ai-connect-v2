from pydantic import BaseModel
from fastapi import APIRouter, Request

router = APIRouter(prefix="/debug", tags=["Debug"])


class DebugMessageRequest(BaseModel):
    sender_mobile: str
    message: str


@router.post("/message")
def debug_message(
    payload: DebugMessageRequest,
    request: Request
) -> dict:
    container = request.app.state.container

    reply = container.conversation_service.process(
        sender_mobile=payload.sender_mobile,
        message=payload.message
    )

    return {
        "sender_mobile": payload.sender_mobile,
        "message": payload.message,
        "reply": reply
    }
