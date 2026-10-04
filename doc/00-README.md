# gemini_live_voice_poc — Documentation Index

Reference material from building this POC, kept so we don't have to re-derive or re-debug the
same things next time.

## Files

- [`01-pcm-audio-fundamentals.md`](./01-pcm-audio-fundamentals.md) — the binary/audio primer:
  bits, bytes, hex, endianness, two's complement, PCM encoding, clipping, chunking. Everything
  needed to read or write raw-audio code without guessing.
- [`02-technical-issues-and-fixes.md`](./02-technical-issues-and-fixes.md) — every real bug hit
  while building this POC: symptom, root cause, fix. Check here first before re-debugging
  something that looks familiar.

## What this project is

A Gemini Live API (voice-to-voice, `gemini-3.8-live`) experiment: a general-purpose voice
assistant with `google_search` grounding plus two custom tools (`set_mood_light`,
`play_sound_effect`). See `main.py` / `tools.py` in the project root for the actual code.
