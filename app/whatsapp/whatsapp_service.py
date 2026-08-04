from typing import Any

import httpx


class WhatsAppService:
    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: str
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version

    def is_configured(self) -> bool:
        return bool(
            self.access_token
            and self.phone_number_id
            and self.api_version
        )

    def send_text_message(
        self,
        recipient_mobile: str,
        message: str
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "status": "NOT_CONFIGURED"
            }

        url = (
            "https://graph.facebook.com/"
            f"{self.api_version}/"
            f"{self.phone_number_id}/messages"
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "".join(
                character
                for character in str(recipient_mobile)
                if character.isdigit()
            ),
            "type": "text",
            "text": {
                "preview_url": False,
                "body": str(message).strip()
            }
        }

        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=30.0
            )

            try:
                body = response.json()
            except ValueError:
                body = {"raw_response": response.text}

            success = 200 <= response.status_code < 300

            return {
                "success": success,
                "status": (
                    "SENT_TO_PROVIDER"
                    if success
                    else "PROVIDER_HTTP_ERROR"
                ),
                "http_status": response.status_code,
                "provider_response": body,
                "provider_message_id": self._message_id(body)
            }

        except httpx.TimeoutException:
            return {
                "success": False,
                "status": "TIMEOUT"
            }

        except httpx.HTTPError as error:
            return {
                "success": False,
                "status": "NETWORK_ERROR",
                "error": str(error)
            }

    @staticmethod
    def _message_id(body: dict[str, Any]):
        messages = body.get("messages", [])

        if not messages:
            return None

        first = messages[0]

        if not isinstance(first, dict):
            return None

        return first.get("id")
