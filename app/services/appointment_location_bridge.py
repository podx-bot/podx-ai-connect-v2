from app.models.session import ConversationStep


def consume_appointment_location(container, incoming) -> str | None:
    """Attach a WhatsApp shared location to an active appointment flow.

    The user's coordinates are stored in the existing user location record so a
    future nearby-business matcher can reuse the same source of truth. The
    appointment request keeps a readable place label while the session advances
    directly to the combined date/time prompt.
    """
    session = container.session_registry.get(incoming.sender_mobile)
    if session.step != ConversationStep.APPOINTMENT_AREA:
        return None

    container.user_repository.save_location(
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
    container.session_registry.save(incoming.sender_mobile)

    return (
        "📍 Location తీసుకున్నాను. ఇప్పుడు రోజు + సమయం ఒకేసారి చెప్పండి. "
        "ఉదా: Tomorrow 4 PM."
    )
