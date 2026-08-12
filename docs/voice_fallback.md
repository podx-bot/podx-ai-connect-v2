# PODX voice transcription fallback

Fast path:
1. Try the existing Gemini Interactions transcription once.
2. If it fails, normalize WhatsApp OGG/Opus to mono 16 kHz WAV with ffmpeg.
3. Transcribe the normalized WAV with Gemini generateContent inline audio.
4. If ffmpeg normalization fails, try generateContent with the original audio bytes.

This keeps the common case fast while giving failed WhatsApp voice notes an independent fallback API path.
