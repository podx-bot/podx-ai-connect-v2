# PODX voice language policy

- Detect and preserve the user's spoken language.
- Telugu or Telugu-English mixed speech should be transcribed in Telugu script where appropriate, while preserving clear English business names, dates, times, and numbers.
- Do not translate the user's meaning during transcription.
- Replies should follow the user's language; Telugu input should receive Telugu conversational prompts.
- Voice transcription fallback order: direct Interactions audio -> normalized mono 16 kHz WAV -> Gemini generateContent audio -> original audio generateContent fallback.
