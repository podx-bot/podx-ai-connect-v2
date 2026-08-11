import subprocess
from typing import Any

import imageio_ffmpeg


class AudioCodecService:
    """Convert Gemini 24 kHz mono PCM into WhatsApp voice-note OGG/Opus."""

    def pcm_to_ogg_opus(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
    ) -> dict[str, Any]:
        if not pcm_bytes:
            return {"success": False, "status": "EMPTY_PCM"}

        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            command = [
                ffmpeg_exe,
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
            return {"success": False, "status": "FFMPEG_TIMEOUT"}
        except Exception as error:
            return {
                "success": False,
                "status": "FFMPEG_START_ERROR",
                "error": str(error),
            }

        if process.returncode != 0:
            return {
                "success": False,
                "status": "FFMPEG_CONVERSION_ERROR",
                "return_code": process.returncode,
                "error": process.stderr.decode("utf-8", errors="replace")[-1000:],
            }

        output = bytes(process.stdout)
        if not output:
            return {"success": False, "status": "EMPTY_OGG"}

        return {
            "success": True,
            "status": "CONVERTED",
            "content": output,
            "mime_type": "audio/ogg",
            "file_name": "podx-reply.ogg",
        }
