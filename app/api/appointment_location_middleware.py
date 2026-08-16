import json

from fastapi.responses import JSONResponse

from app.services.appointment_location_service import AppointmentLocationService
from app.whatsapp.payload_parser import extract_location_messages


class AppointmentLocationMiddleware:
    """Handle location-sensitive flows before the main webhook route.

    Appointment location keeps first priority. If no appointment is waiting, a
    pending Universal Flow request can consume the shared GPS location. Active
    mobile vendors are third priority. Other location webhooks are replayed
    untouched to the existing route.
    """

    def __init__(self, app, container) -> None:
        self.app = app
        self.container = container
        self.service = AppointmentLocationService(
            user_repository=container.user_repository,
            session_registry=container.session_registry,
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("path") != "/webhook":
            await self.app(scope, receive, send)
            return

        body_parts = []
        more_body = True
        while more_body:
            message = await receive()
            body_parts.append(message.get("body", b""))
            more_body = bool(message.get("more_body", False))
        body = b"".join(body_parts)

        async def replay_receive():
            nonlocal body
            replay = body
            body = b""
            return {"type": "http.request", "body": replay, "more_body": False}

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            locations = extract_location_messages(payload)
        except Exception:
            locations = []

        handled = []
        for incoming in locations:
            reply_text = self.service.handle(incoming)
            flow_name = "appointment"
            if reply_text is None:
                reply_text = self.container.universal_live_capture_service.handle_location(
                    sender_mobile=incoming.sender_mobile,
                    latitude=incoming.latitude,
                    longitude=incoming.longitude,
                    location_name=incoming.name,
                    location_address=incoming.address,
                )
                flow_name = "universal"
            if reply_text is None:
                vendor_runtime = getattr(
                    getattr(self.container, "product_buyer_runtime_service", None),
                    "street_vendor_runtime",
                    None,
                )
                if vendor_runtime is not None:
                    reply_text = vendor_runtime.handle_shared_location(
                        vendor_mobile=incoming.sender_mobile,
                        latitude=incoming.latitude,
                        longitude=incoming.longitude,
                    )
                    flow_name = "street_vendor"
            if reply_text is None:
                continue

            if not self.container.inbound_message_repository.exists(incoming.provider_message_id):
                self.container.inbound_message_repository.save(
                    provider_message_id=incoming.provider_message_id,
                    sender_mobile=incoming.sender_mobile,
                    message_text=f"LOCATION:{incoming.latitude:.7f},{incoming.longitude:.7f}",
                )

            send_result = self.container.whatsapp_service.send_text_message(
                recipient_mobile=incoming.sender_mobile,
                message=reply_text,
            )
            handled.append(
                {
                    "flow": flow_name,
                    "sender_mobile": incoming.sender_mobile,
                    "latitude": incoming.latitude,
                    "longitude": incoming.longitude,
                    "reply": reply_text,
                    "send_result": send_result,
                }
            )

        if handled:
            response = JSONResponse(
                {
                    "status": "location_processed",
                    "incoming_location_count": len(handled),
                    "replies": handled,
                }
            )
            await response(scope, replay_receive, send)
            return

        await self.app(scope, replay_receive, send)
