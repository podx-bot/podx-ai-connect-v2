import base64
from typing import Any, Optional

import httpx


class VoiceAssistantService:
    """Convert short WhatsApp voice notes to text for the existing PODX flows."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        max_audio_bytes: int = 18 * 1024 * 1024,
    ) -> None:
        self.api_key = str(api_key).strip()
        self.model = str(model).strip() or "gemini-2.5-flash"
        self.max_audio_bytes = max(1, int(max_audio_bytes))

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def transcribe(self, audio_bytes: bytes, mime_type: Optional[str]) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "status": "NOT_CONFIGURED"}
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}
        if len(audio_bytes) > self.max_audio_bytes:
            return {
                "success": False,
                "status": "AUDIO_TOO_LARGE",
                "max_bytes": self.max_audio_bytes,
                "actual_bytes": len(audio_bytes),
            }

        effective_mime = self._normalize_mime_type(mime_type)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        prompt = (
            "Transcribe only the spoken words in this audio. "
            "The speaker may use Telugu, English, Hindi, or mixed speech. "
            "Preserve the speaker's language and meaning. "
            "For spoken phone numbers, output digits when clear. "
            "Do not explain, summarize, translate, add labels, or add punctuation "
            "that was not needed. Return only the transcription text."
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": effective_mime,
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 256,
            },
        }

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=90.0)
            try:
                body = response.json()
            except ValueError:
                body = {"raw_response": response.text}

            if not (200 <= response.status_code < 300):
                return {
                    "success": False,
                    "status": "GEMINI_HTTP_ERROR",
                    "http_status": response.status_code,
                    "provider_response": body,
                }

            transcript = self._extract_text(body)
            if not transcript:
                return {
                    "success": False,
                    "status": "EMPTY_TRANSCRIPT",
                    "provider_response": body,
                }
            return {
                "success": True,
                "status": "TRANSCRIBED",
                "transcript": transcript,
                "mime_type": effective_mime,
            }
        except httpx.TimeoutException:
            return {"success": False, "status": "GEMINI_TIMEOUT"}
        except httpx.HTTPError as error:
            return {
                "success": False,
                "status": "GEMINI_NETWORK_ERROR",
                "error": str(error),
            }

    @staticmethod
    def normalize_spoken_choice(text: str) -> str:
        clean = " ".join(str(text).strip().split())
        lowered = clean.lower()
        exact_numbers = {
            "ఒకటి": "1",
            "ఒక్కటి": "1",
            "one": "1",
            "రెండు": "2",
            "two": "2",
            "మూడు": "3",
            "three": "3",
            "నాలుగు": "4",
            "four": "4",
            "ఐదు": "5",
            "five": "5",
            "ఆరు": "6",
            "six": "6",
            "ఏడు": "7",
            "seven": "7",
            "ఎనిమిది": "8",
            "eight": "8",
            "తొమ్మిది": "9",
            "nine": "9",
        }
        return exact_numbers.get(lowered, clean)

    @staticmethod
    def _normalize_mime_type(mime_type: Optional[str]) -> str:
        raw = str(mime_type or "audio/ogg").strip().lower()
        # WhatsApp voice notes commonly include codec parameters such as
        # audio/ogg; codecs=opus. Gemini expects the base MIME type.
        return raw.split(";", 1)[0].strip() or "audio/ogg"

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        candidates = body.get("candidates", [])
        if not candidates or not isinstance(candidates[0], dict):
            return ""
        content = candidates[0].get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                return str(part["text"]).strip().strip('"')
        return ""
