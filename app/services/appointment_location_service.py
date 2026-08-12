from app.models.session import ConversationStep


class AppointmentLocationService:
    """Attach a WhatsApp shared location to an active appointment flow."""

    def __init__(self, user_repository, session_registry) -> None:
        self.user_repository = user_repository
        self.session_registry = session_registry

    def handle(self, incoming) -> str | None:
        session = self.session_registry.get(incoming.sender_mobile)
        if session.step != ConversationStep.APPOINTMENT_AREA:
            return None

        self.user_repository.save_location(
            whatsapp_mobile=incoming.sender_mobile,
            latitude=incoming.latitude,
            longitude=incoming.longitude,
            location_name=incoming.name,
            location_address=incoming.address,
        )

        place_label = (
            (incoming.name or "").strip()
            or (incoming.address or "").strip()
            or "Current location"
        )
        session.data["appointment_area"] = place_label
        session.data["appointment_latitude"] = incoming.latitude
        session.data["appointment_longitude"] = incoming.longitude
        session.step = ConversationStep.APPOINTMENT_DATE
        self.session_registry.save(incoming.sender_mobile)

        return (
            "📍 Location తీసుకున్నాను. ఇప్పుడు రోజు + సమయం ఒకేసారి చెప్పండి. "
            "ఉదా: Tomorrow 4 PM."
        )
