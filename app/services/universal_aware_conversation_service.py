"""Thin live adapter for Universal Flow responses, image clarification and capture."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class UniversalAwareConversationService:
    GREETING_WORDS = {"hi", "hello", "hey", "హాయ్", "హలో", "नमस्ते", "हाय"}

    def __init__(self, response_commands, base_conversation, live_capture=None, image_service=None) -> None:
        self.response_commands = response_commands
        self.live_capture = live_capture
        self.image_service = image_service
        self.base_conversation = base_conversation

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        normalized = clean_message.casefold()

        # A greeting from an already registered user is a conversational welcome-back,
        # not a menu dump. Keep this before all universal capture/router layers so a
        # simple "Hi" can never be reclassified into another workflow.
        if normalized in self.GREETING_WORDS:
            welcome = self._registered_welcome_back(sender_mobile)
            if welcome is not None:
                return welcome

        response_reply = self.response_commands.process_text(
            sender_mobile=sender_mobile,
            message=clean_message,
        )
        if response_reply is not None:
            return response_reply

        if self.image_service is not None:
            image_reply = self.image_service.process_text(
                sender_mobile=sender_mobile,
                message=clean_message,
            )
            if image_reply is not None:
                return image_reply

        if self.live_capture is not None:
            capture_reply = self.live_capture.process_text(
                sender_mobile=sender_mobile,
                message=clean_message,
            )
            if capture_reply is not None:
                return capture_reply

        return self.base_conversation.process(
            sender_mobile=sender_mobile,
            message=clean_message,
        )

    def _registered_welcome_back(self, sender_mobile: str) -> str | None:
        user_repository = getattr(self.base_conversation, "user_repository", None)
        session_registry = getattr(self.base_conversation, "session_registry", None)
        if user_repository is None:
            return None

        user = user_repository.find_by_whatsapp_mobile(sender_mobile)
        if not user or user.get("registration_complete") != 1:
            return None

        # A fresh greeting intentionally exits stale workflows and returns the user
        # to an open conversational state without showing the old menu/examples.
        if session_registry is not None:
            session = session_registry.get(sender_mobile)
            try:
                from app.models.session import ConversationStep
                session.step = ConversationStep.MAIN_MENU
                session.data.clear()
                session_registry.save(sender_mobile)
            except Exception:
                pass

        name = str(user.get("name") or "").strip()
        language = str(user.get("language") or "English").strip().casefold()
        hour = datetime.now(ZoneInfo("Asia/Kolkata")).hour

        if hour < 12:
            period = "morning"
        elif hour < 17:
            period = "afternoon"
        else:
            period = "evening"

        if language == "telugu":
            wish = {
                "morning": "శుభోదయం",
                "afternoon": "శుభ మధ్యాహ్నం",
                "evening": "శుభ సాయంత్రం",
            }[period]
            person = f", {name} గారు" if name else ""
            return (
                f"👋 {wish}{person}! PODXకి మళ్లీ స్వాగతం.\n\n"
                "ఈరోజు మీకు ఎలా సహాయం చేయగలను? మీకు కావాల్సింది మీ మాటల్లో 🎙️ voiceగా లేదా ⌨️ textగా చెప్పండి."
            )

        if language == "hindi":
            wish = {
                "morning": "सुप्रभात",
                "afternoon": "शुभ दोपहर",
                "evening": "शुभ संध्या",
            }[period]
            person = f", {name} जी" if name else ""
            return (
                f"👋 {wish}{person}! PODX में आपका फिर से स्वागत है।\n\n"
                "आज मैं आपकी कैसे मदद कर सकता हूँ? जो चाहिए उसे अपनी भाषा में 🎙️ voice या ⌨️ text में बताइए।"
            )

        wish = {
            "morning": "Good morning",
            "afternoon": "Good afternoon",
            "evening": "Good evening",
        }[period]
        person = f", {name}" if name else ""
        return (
            f"👋 {wish}{person}! Welcome back to PODX.\n\n"
            "How may I help you today? Tell me what you need in your own words by 🎙️ voice or ⌨️ text."
        )
