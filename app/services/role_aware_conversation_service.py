from app.models.session import ConversationStep
from app.services.intent_aware_conversation_service import IntentAwareConversationService


class RoleAwareConversationService(IntentAwareConversationService):
    """Allow registered users to add PODX roles without re-registering."""

    ROLE_COMMANDS = {
        "roles",
        "my roles",
        "manage roles",
        "add roles",
        "change roles",
        "నా roles",
        "నా రోల్స్",
        "roles మార్చాలి",
        "రోల్స్ మార్చాలి",
        "roles add చేయాలి",
        "రోల్స్ యాడ్ చేయాలి",
    }

    ROLE_DONE_COMMANDS = {
        "done",
        "exit",
        "finish",
        "finished",
        "complete",
        "close",
        "అయింది",
        "పూర్తి",
        "ముగించు",
        "బయటకు",
    }

    def process(self, sender_mobile: str, message: str) -> str:
        clean_message = str(message or "").strip()
        normalized = clean_message.lower()
        session = self.session_registry.get(sender_mobile)
        existing_user = self.user_repository.find_by_whatsapp_mobile(sender_mobile)
        registered = bool(existing_user and existing_user.get("registration_complete") == 1)

        if registered and normalized in self.ROLE_COMMANDS:
            session.data.clear()
            session.data["manage_roles"] = True
            session.step = ConversationStep.WAITING_CAPABILITIES
            current = existing_user.get("capabilities") or []
            current_text = ", ".join(
                self.CAPABILITY_LABELS.get(item, item) for item in current
            ) or "None yet"
            return self._reply(
                sender_mobile,
                f"⚙️ మీ current PODX roles: {current_text}\n\n"
                "కొత్త roles add చేయడానికి ఒకటి లేదా ఎక్కువ options ఎంచుకోండి.\n"
                "ఒక్కొక్కటిగా కూడా పంపవచ్చు: 1 తర్వాత 2 తర్వాత 4.\n"
                "పూర్తయ్యాక Done అని పంపండి.\n\n"
                + self._capability_menu(),
            )

        if (
            registered
            and session.step == ConversationStep.WAITING_CAPABILITIES
            and session.data.get("manage_roles")
        ):
            if normalized in self.ROLE_DONE_COMMANDS:
                return self._finish_manage_roles(sender_mobile, session)

            capabilities = self._parse_capabilities(clean_message)
            if not capabilities:
                return self._reply(
                    sender_mobile,
                    "ఒకటి లేదా ఎక్కువ valid options ఎంచుకోండి. ఉదాహరణ: 1 లేదా 1,2.\n"
                    "పూర్తయ్యాక Done అని పంపండి.\n\n"
                    + self._capability_menu(),
                )

            self.user_repository.add_capabilities(
                sender_mobile,
                capabilities,
                source="profile_manage",
            )

            # A comma-separated batch is already a complete multi-role selection.
            # A single numeric choice stays locked inside Manage Roles so the next
            # number cannot accidentally trigger another workflow.
            if len(capabilities) > 1:
                return self._finish_manage_roles(sender_mobile, session)

            all_capabilities = self.user_repository.list_capabilities(sender_mobile)
            selected = ", ".join(
                self.CAPABILITY_LABELS.get(item, item) for item in all_capabilities
            )
            return self._reply(
                sender_mobile,
                f"✅ Role add అయ్యింది. Current roles: {selected}\n\n"
                "మరొక role number పంపండి, లేదా పూర్తయ్యాక Done అని పంపండి.\n\n"
                + self._capability_menu(),
            )

        return super().process(sender_mobile, clean_message)

    def _finish_manage_roles(self, sender_mobile, session) -> str:
        session.data.clear()
        session.step = ConversationStep.MAIN_MENU
        all_capabilities = self.user_repository.list_capabilities(sender_mobile)
        selected = ", ".join(
            self.CAPABILITY_LABELS.get(item, item) for item in all_capabilities
        ) or "None yet"
        return self._reply(
            sender_mobile,
            f"✅ మీ PODX roles update అయ్యాయి: {selected}\n\n" + self._main_menu(),
        )
