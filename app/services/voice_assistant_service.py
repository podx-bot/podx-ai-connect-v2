import base64
import re
from typing import Any, Optional

from google import genai


class VoiceAssistantService:
    """Understand WhatsApp voice notes and synthesize PODX spoken replies."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.6-flash",
        max_audio_bytes: int = 18 * 1024 * 1024,
        tts_model: str = "gemini-3.1-flash-tts-preview",
        tts_voice: str = "Sulafat",
        voice_reply_max_chars: int = 900,
    ) -> None:
        self.api_key = str(api_key).strip()
        self.model = str(model).strip() or "gemini-3.6-flash"
        self.max_audio_bytes = max(1, int(max_audio_bytes))
        self.tts_model = str(tts_model).strip() or "gemini-3.1-flash-tts-preview"
        self.tts_voice = str(tts_voice).strip() or "Sulafat"
        self.voice_reply_max_chars = max(100, int(voice_reply_max_chars))

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def is_tts_configured(self) -> bool:
        return bool(self.api_key and self.tts_model and self.tts_voice)

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
        prompt = (
            "Transcribe only the spoken words in this audio. "
            "The speaker may use Telugu, English, Hindi, or mixed speech. "
            "Preserve the speaker's language and meaning. "
            "For spoken phone numbers, output digits when clear. "
            "Do not explain, summarize, translate, add labels, or add punctuation "
            "that was not needed. Return only the transcription text."
        )

        try:
            client = genai.Client(api_key=self.api_key)
            interaction = client.interactions.create(
                model=self.model,
                input=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "audio",
                        "data": base64.b64encode(audio_bytes).decode("ascii"),
                        "mime_type": effective_mime,
                    },
                ],
                store=False,
            )
            transcript = str(getattr(interaction, "output_text", "") or "").strip().strip('"')
            if not transcript:
                return {
                    "success": False,
                    "status": "EMPTY_TRANSCRIPT",
                    "model": self.model,
                }
            return {
                "success": True,
                "status": "TRANSCRIBED",
                "transcript": transcript,
                "mime_type": effective_mime,
                "model": self.model,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "GEMINI_TRANSCRIPTION_ERROR",
                "error": str(error),
                "model": self.model,
            }

    def synthesize(self, text: str) -> dict[str, Any]:
        """Generate 24 kHz mono signed-16-bit PCM for a short PODX reply."""
        if not self.is_tts_configured():
            return {"success": False, "status": "TTS_NOT_CONFIGURED"}

        spoken_text = self.prepare_spoken_text(text)
        if not spoken_text:
            return {"success": False, "status": "EMPTY_TTS_TEXT"}

        prompt = (
            "Speak the following PODX WhatsApp reply naturally and clearly. "
            "Use the language already present in the reply. "
            "For Telugu, use a warm, friendly Telugu speaking style. "
            "Keep a moderate pace suitable for a user who may prefer listening "
            "instead of reading. Do not add any new information.\n\n"
            f"Reply:\n{spoken_text}"
        )

        try:
            client = genai.Client(api_key=self.api_key)
            interaction = client.interactions.create(
                model=self.tts_model,
                input=prompt,
                response_format={"type": "audio"},
                generation_config={
                    "speech_config": [
                        {"voice": self.tts_voice}
                    ]
                },
                store=False,
            )
            output_audio = getattr(interaction, "output_audio", None)
            audio_data = getattr(output_audio, "data", None) if output_audio else None
            if not audio_data:
                return {"success": False, "status": "EMPTY_TTS_AUDIO"}

            if isinstance(audio_data, bytes):
                pcm_bytes = audio_data
            else:
                pcm_bytes = base64.b64decode(str(audio_data))

            if not pcm_bytes:
                return {"success": False, "status": "EMPTY_TTS_PCM"}

            return {
                "success": True,
                "status": "SYNTHESIZED",
                "content": pcm_bytes,
                "sample_rate": 24000,
                "channels": 1,
                "sample_width": 2,
                "spoken_text": spoken_text,
                "model": self.tts_model,
                "voice": self.tts_voice,
            }
        except Exception as error:
            return {
                "success": False,
                "status": "TTS_GENERATION_ERROR",
                "error": str(error),
            }

    def prepare_spoken_text(self, text: str) -> str:
        clean = str(text or "").strip()
        if not clean:
            return ""

        clean = re.sub(
            r"https?://\S+",
            " లింక్ టెక్స్ట్ మెసేజ్‌లో ఉంది ",
            clean,
            flags=re.IGNORECASE,
        )
        clean = clean.replace("#", " నంబర్ ")
        clean = " ".join(clean.split())
        if len(clean) > self.voice_reply_max_chars:
            clean = clean[: self.voice_reply_max_chars].rsplit(" ", 1)[0].strip()
        return clean

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
        return raw.split(";", 1)[0].strip() or "audio/ogg"
