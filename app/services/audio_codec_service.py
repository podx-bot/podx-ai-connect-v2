import subprocess
import time
from typing import Any

import imageio_ffmpeg


class AudioCodecService:
    """Convert audio formats used by Gemini and WhatsApp."""

    @staticmethod
    def _ffmpeg_exe() -> str:
        return imageio_ffmpeg.get_ffmpeg_exe()

    def audio_to_wav(self, audio_bytes: bytes) -> dict[str, Any]:
        """Normalize WhatsApp OGG/Opus (or other decodable audio) to mono 16 kHz WAV."""
        if not audio_bytes:
            return {"success": False, "status": "EMPTY_AUDIO"}
        try:
            process = subprocess.run(
                [
                    self._ffmpeg_exe(),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    "pipe:0",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    "pipe:1",
                ],
                input=audio_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "status": "FFMPEG_NORMALIZE_TIMEOUT"}
        except Exception as error:
            return {"success": False, "status": "FFMPEG_NORMALIZE_START_ERROR", "error": str(error)}

        if process.returncode != 0:
            return {
                "success": False,
                "status": "FFMPEG_NORMALIZE_ERROR",
                "error": process.stderr.decode("utf-8", errors="replace")[-1000:],
            }
        output = bytes(process.stdout)
        if not output:
            return {"success": False, "status": "EMPTY_WAV"}
        return {"success": True, "status": "NORMALIZED", "content": output, "mime_type": "audio/wav"}

    def pcm_to_ogg_opus(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
    ) -> dict[str, Any]:
        if not pcm_bytes:
            return {"success": False, "status": "EMPTY_PCM"}

        if pcm_bytes.startswith(b"OggS"):
            return {
                "success": True,
                "status": "ALREADY_OGG_OPUS",
                "content": pcm_bytes,
                "mime_type": "audio/ogg",
                "file_name": "podx-reply.ogg",
                "conversion_ms": 0,
                "conversion_bypass": True,
            }

        started = time.perf_counter()
        try:
            command = [
                self._ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "s16le",
                "-ar",
                str(int(sample_rate)),
                "-ac",
                str(int(channels)),
                "-i",
                "pipe:0",
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-vbr",
                "on",
                "-application",
                "voip",
                "-f",
                "ogg",
                "pipe:1",
            ]
            process = subprocess.run(
                command,
                input=pcm_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "status": "FFMPEG_TIMEOUT",
                "conversion_ms": round((time.perf_counter() - started) * 1000),
            }
        except Exception as error:
            return {
                "success": False,
                "status": "FFMPEG_START_ERROR",
                "error": str(error),
                "conversion_ms": round((time.perf_counter() - started) * 1000),
            }

        conversion_ms = round((time.perf_counter() - started) * 1000)
        if process.returncode != 0:
            return {
                "success": False,
                "status": "FFMPEG_CONVERSION_ERROR",
                "return_code": process.returncode,
                "error": process.stderr.decode("utf-8", errors="replace")[-1000:],
                "conversion_ms": conversion_ms,
            }

        output = bytes(process.stdout)
        if not output:
            return {"success": False, "status": "EMPTY_OGG", "conversion_ms": conversion_ms}

        return {
            "success": True,
            "status": "CONVERTED",
            "content": output,
            "mime_type": "audio/ogg",
            "file_name": "podx-reply.ogg",
            "conversion_ms": conversion_ms,
            "conversion_bypass": False,
        }
