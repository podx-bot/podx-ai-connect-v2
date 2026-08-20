import threading
import time
from typing import Any

import httpx


class WhatsAppService:
    RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
    MAX_AUDIO_BYTES = 16 * 1024 * 1024
    STATUS_DUPLICATE_WINDOW_SECONDS = 10 * 60
    STATUS_MESSAGE_MARKERS = (
        "wait",
        "waiting",
        "pending",
        "confirmation",
        "confirm కోసం",
        "availability",
        "అందుబాటు",
        "వేచి",
    )

    def __init__(
        self,
        access_token,
        phone_number_id,
        api_version,
        max_attempts=3,
        retry_delay_seconds=0.5,
    ):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0, float(retry_delay_seconds))
        self._recent_status_messages = {}
        self._recent_status_lock = threading.RLock()
        self._http_client = httpx.Client(
            timeout=httpx.Timeout(connect=3, read=60, write=60, pool=3),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30,
            ),
        )

    def is_configured(self):
        return bool(self.access_token and self.phone_number_id and self.api_version)

    def close(self):
        self._http_client.close()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _messages_url(self):
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def _send_with_retry(self, payload):
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED", "attempts": 0}
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        last = {}
        for attempt in range(1, self.max_attempts + 1):
            last = self._send_once(self._messages_url(), headers, payload)
            last["attempts"] = attempt
            if last.get("success") or not last.get("retryable") or attempt >= self.max_attempts:
                return last
            if self.retry_delay_seconds:
                time.sleep(self.retry_delay_seconds * attempt)
        return last

    @staticmethod
    def _mobile(mobile):
        return "".join(char for char in str(mobile) if char.isdigit())

    @classmethod
    def _looks_like_status_message(cls, message):
        lowered = str(message or "").strip().casefold()
        return bool(lowered and any(marker in lowered for marker in cls.STATUS_MESSAGE_MARKERS))

    def _is_recent_duplicate_status(self, recipient_mobile, message):
        body = str(message or "").strip()
        if not self._looks_like_status_message(body):
            return False
        mobile = self._mobile(recipient_mobile)
        key = (mobile, body.casefold())
        now = time.monotonic()
        with self._recent_status_lock:
            expired = [
                old_key
                for old_key, sent_at in self._recent_status_messages.items()
                if now - sent_at > self.STATUS_DUPLICATE_WINDOW_SECONDS
            ]
            for old_key in expired:
                self._recent_status_messages.pop(old_key, None)
            sent_at = self._recent_status_messages.get(key)
            if sent_at is not None and now - sent_at <= self.STATUS_DUPLICATE_WINDOW_SECONDS:
                return True
            self._recent_status_messages[key] = now
            return False

    def send_text_message(self, recipient_mobile, message):
        clean_message = str(message).strip()
        if self._is_recent_duplicate_status(recipient_mobile, clean_message):
            return {
                "success": True,
                "status": "DUPLICATE_STATUS_SUPPRESSED",
                "attempts": 0,
                "suppressed": True,
            }
        return self._send_with_retry({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._mobile(recipient_mobile),
            "type": "text",
            "text": {"preview_url": False, "body": clean_message},
        })

    def _send_media_by_id(self, recipient_mobile, kind, media_id, caption=""):
        media_id = str(media_id or "").strip()
        if not media_id:
            return {"success": False, "status": "MEDIA_ID_MISSING", "attempts": 0}
        obj = {"id": media_id}
        clean_caption = str(caption or "").strip()
        if clean_caption:
            obj["caption"] = clean_caption[:1024]
        return self._send_with_retry({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._mobile(recipient_mobile),
            "type": kind,
            kind: obj,
        })

    def send_image_by_id(self, recipient_mobile, media_id, caption=""):
        return self._send_media_by_id(recipient_mobile, "image", media_id, caption)

    def send_video_by_id(self, recipient_mobile, media_id, caption=""):
        return self._send_media_by_id(recipient_mobile, "video", media_id, caption)

    def send_reply_buttons(self, recipient_mobile, body, buttons):
        actions = []
        for item in buttons[:3]:
            button_id = str(item.get("id") or "").strip()[:256]
            title = str(item.get("title") or "").strip()[:20]
            if button_id and title:
                actions.append({"type": "reply", "reply": {"id": button_id, "title": title}})
        if not actions:
            return self.send_text_message(recipient_mobile, body)
        return self._send_with_retry({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._mobile(recipient_mobile),
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": str(body).strip()},
                "action": {"buttons": actions},
            },
        })

    def upload_audio(self, audio_bytes, mime_type="audio/ogg", file_name="podx-reply.ogg"):
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}
        if len(audio_bytes) > self.MAX_AUDIO_BYTES:
            return {"success": False, "status": "AUDIO_TOO_LARGE", "actual_bytes": len(audio_bytes), "max_bytes": self.MAX_AUDIO_BYTES}
        try:
            response = self._http_client.post(
                f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media",
                headers=self._auth_headers(),
                data={"messaging_product": "whatsapp"},
                files={"file": (str(file_name), audio_bytes, str(mime_type or "audio/ogg"))},
                timeout=60,
            )
            body = self._safe_json(response)
            if not 200 <= response.status_code < 300:
                return {"success": False, "status": "MEDIA_UPLOAD_HTTP_ERROR", "http_status": response.status_code, "provider_response": body}
            media_id = str(body.get("id", "")).strip()
            if not media_id:
                return {"success": False, "status": "MEDIA_ID_MISSING", "provider_response": body}
            return {"success": True, "status": "UPLOADED", "media_id": media_id, "provider_response": body}
        except httpx.TimeoutException:
            return {"success": False, "status": "MEDIA_UPLOAD_TIMEOUT"}
        except httpx.HTTPError as exc:
            return {"success": False, "status": "MEDIA_UPLOAD_NETWORK_ERROR", "error": str(exc)}

    def send_audio_by_id(self, recipient_mobile, media_id, as_voice_message=True):
        media_id = str(media_id).strip()
        if not media_id:
            return {"success": False, "status": "MEDIA_ID_MISSING", "attempts": 0}
        obj = {"id": media_id}
        if as_voice_message:
            obj["voice"] = True
        return self._send_with_retry({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._mobile(recipient_mobile),
            "type": "audio",
            "audio": obj,
        })

    def send_voice_bytes(self, recipient_mobile=None, audio_bytes=None, mime_type="audio/ogg", file_name="podx-reply.ogg", m=None):
        mobile = recipient_mobile if recipient_mobile is not None else m
        start = time.perf_counter()
        upload = self.upload_audio(audio_bytes, mime_type, file_name)
        upload_ms = round((time.perf_counter() - start) * 1000)
        if not upload.get("success"):
            return {"success": False, "status": "VOICE_UPLOAD_FAILED", "upload_result": upload, "upload_ms": upload_ms}
        send_start = time.perf_counter()
        result = self.send_audio_by_id(mobile, upload["media_id"], True)
        return {
            **result,
            "media_id": upload["media_id"],
            "upload_result": upload,
            "upload_ms": upload_ms,
            "message_send_ms": round((time.perf_counter() - send_start) * 1000),
            "voice_send_total_ms": round((time.perf_counter() - start) * 1000),
        }

    def download_media(self, media_id):
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        start = time.perf_counter()
        try:
            metadata_start = time.perf_counter()
            metadata_response = self._http_client.get(
                f"https://graph.facebook.com/{self.api_version}/{str(media_id).strip()}",
                headers=self._auth_headers(),
                timeout=30,
            )
            metadata_ms = round((time.perf_counter() - metadata_start) * 1000)
            if not 200 <= metadata_response.status_code < 300:
                return {"success": False, "status": "MEDIA_METADATA_HTTP_ERROR", "http_status": metadata_response.status_code, "provider_response": self._safe_json(metadata_response), "metadata_ms": metadata_ms}
            metadata_body = metadata_response.json()
            url = str(metadata_body.get("url", "")).strip()
            if not url:
                return {"success": False, "status": "MEDIA_URL_MISSING", "provider_response": metadata_body, "metadata_ms": metadata_ms}
            download_start = time.perf_counter()
            media_response = self._http_client.get(url, headers=self._auth_headers(), timeout=60)
            download_ms = round((time.perf_counter() - download_start) * 1000)
            if not 200 <= media_response.status_code < 300:
                return {"success": False, "status": "MEDIA_DOWNLOAD_HTTP_ERROR", "http_status": media_response.status_code, "metadata_ms": metadata_ms, "download_ms": download_ms}
            return {
                "success": True,
                "status": "DOWNLOADED",
                "content": media_response.content,
                "mime_type": metadata_body.get("mime_type") or media_response.headers.get("content-type"),
                "file_size": len(media_response.content),
                "metadata_ms": metadata_ms,
                "download_ms": download_ms,
                "media_total_ms": round((time.perf_counter() - start) * 1000),
            }
        except httpx.TimeoutException:
            return {"success": False, "status": "MEDIA_TIMEOUT"}
        except (httpx.HTTPError, ValueError) as exc:
            return {"success": False, "status": "MEDIA_NETWORK_ERROR", "error": str(exc)}

    def _send_once(self, url, headers, payload):
        try:
            response = self._http_client.post(url, headers=headers, json=payload, timeout=30)
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
        except httpx.HTTPError as exc:
            return {"success": False, "status": "NETWORK_ERROR", "error": str(exc), "retryable": True}

    @staticmethod
    def _safe_json(response):
        try:
            value = response.json()
            return value if isinstance(value, dict) else {"value": value}
        except ValueError:
            return {"raw_response": response.text}

    @staticmethod
    def _message_id(body):
        messages = body.get("messages", [])
        return messages[0].get("id") if messages and isinstance(messages[0], dict) else None
