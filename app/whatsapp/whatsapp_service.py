import time
from typing import Any

import httpx


class WhatsAppService:
    RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.5
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id and self.api_version)

    def send_text_message(self, recipient_mobile: str, message: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED", "attempts": 0}

        url = "https://graph.facebook.com/" f"{self.api_version}/" f"{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "".join(character for character in str(recipient_mobile) if character.isdigit()),
            "type": "text",
            "text": {"preview_url": False, "body": str(message).strip()}
        }

        last_result: dict[str, Any] = {}
        for attempt in range(1, self.max_attempts + 1):
            last_result = self._send_once(url, headers, payload)
            last_result["attempts"] = attempt

            if last_result.get("success"):
                return last_result

            if not last_result.get("retryable") or attempt >= self.max_attempts:
                return last_result

            if self.retry_delay_seconds:
                time.sleep(self.retry_delay_seconds * attempt)

        return last_result

    def _send_once(self, url: str, headers: dict, payload: dict) -> dict[str, Any]:
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
            try:
                body = response.json()
            except ValueError:
                body = {"raw_response": response.text}

            success = 200 <= response.status_code < 300
            return {
                "success": success,
                "status": "SENT_TO_PROVIDER" if success else "PROVIDER_HTTP_ERROR",
                "http_status": response.status_code,
                "provider_response": body,
                "provider_message_id": self._message_id(body),
                "retryable": response.status_code in self.RETRYABLE_HTTP_STATUS
            }
        except httpx.TimeoutException:
            return {"success": False, "status": "TIMEOUT", "retryable": True}
        except httpx.HTTPError as error:
            return {
                "success": False,
                "status": "NETWORK_ERROR",
                "error": str(error),
                "retryable": True
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
