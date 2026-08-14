# PODX AI CONNECT — Current Checkpoint

Date: 2026-08-14

- Voice reply latency live baseline: ~3 seconds.
- PR #59 merged successfully: Sarvam direct Opus/Ogg TTS path with FFmpeg bypass for valid Ogg/Opus.
- Reliability suite passed: 119 tests.
- Preserve the current fast text/STT/conversation/voice path; do not regress latency.
- Stale open PRs: #24 and #2 should not be merged blindly because current `main` has moved significantly.
- Next clean development task: make clear new intents able to escape stale worker/employer steps such as WORKER_LOCATION, EMPLOYER_REQUIREMENT, and EMPLOYER_LOCATION without corrupting the active workflow.
