import time
from typing import Any

import httpx


class WhatsAppService:
    RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
    MAX_AUDIO_BYTES = 16 * 1024 * 1024

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 0.5,
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(connect=3.0, read=60.0, write=60.0, pool=3.0),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0,
            ),
        )

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id and self.api_version)

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def send_text_message(self, recipient_mobile: str, message: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED", "attempts": 0}

        url = (
            "https://graph.facebook.com/"
            f"{self.api_version}/{self.phone_number_id}/messages"
        )
        headers = {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "".join(
                character for character in str(recipient_mobile) if character.isdigit()
            ),
            "type": "text",
            "text": {"preview_url": False, "body": str(message).strip()},
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

    def upload_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        file_name: str = "podx-reply.ogg",
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}
        if len(audio_bytes) > self.MAX_AUDIO_BYTES:
            return {
                "success": False,
                "status": "AUDIO_TOO_LARGE",
                "actual_bytes": len(audio_bytes),
                "max_bytes": self.MAX_AUDIO_BYTES,
            }

        url = (
            "https://graph.facebook.com/"
            f"{self.api_version}/{self.phone_number_id}/media"
        )
        try:
            response = self._http_client.post(
                url,
                headers=self._auth_headers(),
                data={"messaging_product": "whatsapp"},
                files={
                    "file": (
                        str(file_name),
                        audio_bytes,
                        str(mime_type or "audio/ogg"),
                    )
                },
                timeout=60.0,
            )
            body = self._safe_json(response)
            if not (200 <= response.status_code < 300):
                return {
                    "success": False,
                    "status": "MEDIA_UPLOAD_HTTP_ERROR",
                    "http_status": response.status_code,
                    "provider_response": body,
                }
            media_id = str(body.get("id", "")).strip()
            if not media_id:
                return {
                    "success": False,
                    "status": "MEDIA_ID_MISSING",
                    "provider_response": body,
                }
            return {
                "success": True,
                "status": "UPLOADED",
                "media_id": media_id,
                "provider_response": body,
            }
        except httpx.TimeoutException:
            return {"success": False, "status": "MEDIA_UPLOAD_TIMEOUT"}
        except httpx.HTTPError as error:
            return {
                "success": False,
                "status": "MEDIA_UPLOAD_NETWORK_ERROR",
                "error": str(error),
            }

    def send_audio_by_id(
        self,
        recipient_mobile: str,
        media_id: str,
        as_voice_message: bool = True,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED", "attempts": 0}
        clean_media_id = str(media_id).strip()
        if not clean_media_id:
            return {"success": False, "status": "MEDIA_ID_MISSING", "attempts": 0}

        url = (
            "https://graph.facebook.com/"
            f"{self.api_version}/{self.phone_number_id}/messages"
        )
        headers = {
            **self._auth_headers(),
            "Content-Type": "application/json",
        }
        audio_object: dict[str, Any] = {"id": clean_media_id}
        if as_voice_message:
            audio_object["voice"] = True
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "".join(
                character for character in str(recipient_mobile) if character.isdigit()
            ),
            "type": "audio",
            "audio": audio_object,
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

    def send_voice_bytes(
        self,
        recipient_mobile: str,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        file_name: str = "podx-reply.ogg",
    ) -> dict[str, Any]:
        total_started = time.perf_counter()
        upload_started = total_started
        upload_result = self.upload_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            file_name=file_name,
        )
        upload_ms = round((time.perf_counter() - upload_started) * 1000)
        if not upload_result.get("success"):
            return {
                "success": False,
                "status": "VOICE_UPLOAD_FAILED",
                "upload_result": upload_result,
                "upload_ms": upload_ms,
                "message_send_ms": 0,
                "voice_send_total_ms": round((time.perf_counter() - total_started) * 1000),
            }

        message_started = time.perf_counter()
        send_result = self.send_audio_by_id(
            recipient_mobile=recipient_mobile,
            media_id=upload_result["media_id"],
            as_voice_message=True,
        )
        message_send_ms = round((time.perf_counter() - message_started) * 1000)
        return {
            **send_result,
            "media_id": upload_result["media_id"],
            "upload_result": upload_result,
            "upload_ms": upload_ms,
            "message_send_ms": message_send_ms,
            "voice_send_total_ms": round((time.perf_counter() - total_started) * 1000),
        }

    def download_media(self, media_id: str) -> dict[str, Any]:
        """Resolve a WhatsApp media id and download its bytes using the access token."""
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}

        metadata_url = (
            f"https://graph.facebook.com/{self.api_version}/{str(media_id).strip()}"
        )
        total_started = time.perf_counter()
        try:
            metadata_started = time.perf_counter()
            metadata_response = self._http_client.get(
                metadata_url,
                headers=self._auth_headers(),
                timeout=30.0,
            )
            metadata_ms = round((time.perf_counter() - metadata_started) * 1000)
            if not (200 <= metadata_response.status_code < 300):
                return {
                    "success": False,
                    "status": "MEDIA_METADATA_HTTP_ERROR",
                    "http_status": metadata_response.status_code,
                    "provider_response": self._safe_json(metadata_response),
                    "metadata_ms": metadata_ms,
                    "download_ms": 0,
                    "media_total_ms": round((time.perf_counter() - total_started) * 1000),
                }

            metadata = metadata_response.json()
            download_url = str(metadata.get("url", "")).strip()
            if not download_url:
                return {
                    "success": False,
                    "status": "MEDIA_URL_MISSING",
                    "provider_response": metadata,
                    "metadata_ms": metadata_ms,
                    "download_ms": 0,
                    "media_total_ms": round((time.perf_counter() - total_started) * 1000),
                }

            download_started = time.perf_counter()
            media_response = self._http_client.get(
                download_url,
                headers=self._auth_headers(),
                timeout=60.0,
            )
            download_ms = round((time.perf_counter() - download_started) * 1000)
            if not (200 <= media_response.status_code < 300):
                return {
                    "success": False,
                    "status": "MEDIA_DOWNLOAD_HTTP_ERROR",
                    "http_status": media_response.status_code,
                    "metadata_ms": metadata_ms,
                    "download_ms": download_ms,
                    "media_total_ms": round((time.perf_counter() - total_started) * 1000),
                }

            return {
                "success": True,
                "status": "DOWNLOADED",
                "content": media_response.content,
                "mime_type": metadata.get("mime_type")
                or media_response.headers.get("content-type"),
                "file_size": len(media_response.content),
                "metadata_ms": metadata_ms,
                "download_ms": download_ms,
                "media_total_ms": round((time.perf_counter() - total_started) * 1000),
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "status": "MEDIA_TIMEOUT",
                "media_total_ms": round((time.perf_counter() - total_started) * 1000),
            }
        except (httpx.HTTPError, ValueError) as error:
            return {
                "success": False,
                "status": "MEDIA_NETWORK_ERROR",
                "error": str(error),
                "media_total_ms": round((time.perf_counter() - total_started) * 1000),
            }

    def _send_once(self, url: str, headers: dict, payload: dict) -> dict[str, Any]:
        try:
            response = self._http_client.post(url, headers=headers, json=payload, timeout=30.0)
            body = self._safe_json(response)
            success = 200 <= response.status_code < 300
            return {
                "success": success,
                "status": "SENT_TO_PROVIDER" if success else "PROVIDER_HTTP_ERROR",
                "http_status": response.status_code,
                "provider_response": body,
                "provider_message_id": self._message_id(body),
                "retryable": response.status_code in self.RETRYABLE_HTTP_STATUS,
            }
        except httpx.TimeoutException:
            return {"success": False, "status": "TIMEOUT", "retryable": True}
        except httpx.HTTPError as error:
            return {
                "success": False,
                "status": "NETWORK_ERROR",
                "error": str(error),
                "retryable": True,
            }

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
            return value if isinstance(value, dict) else {"value": value}
        except ValueError:
            return {"raw_response": response.text}

    @staticmethod
    def _message_id(body: dict[str, Any]):
        messages = body.get("messages", [])
        if not messages:
            return None
        first = messages[0]
        if not isinstance(first, dict):
            return None
        return first.get("id")
