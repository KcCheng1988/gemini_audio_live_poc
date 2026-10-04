# Technical Issues Encountered — Symptom, Root Cause, Fix

Real bugs hit while building this POC. Check here before re-debugging something that looks
familiar.

## 1. `pyaudio` fails to install on Windows

**Symptom**: `pip install -r requirements.txt` errors out specifically on `pyaudio`.

**Root cause**: `pyaudio` depends on the PortAudio C library, which plain `pip install` often
can't build from source on Windows.

**Fix**:
```powershell
pip install pipwin
pipwin install pyaudio
```
If that also fails, fall back to a prebuilt wheel matching your Python version (e.g. from
Christoph Gohlke's unofficial Windows wheel archive).

## 2. Wrong/unexpected microphone picked up automatically

**Symptom**: multiple microphones available; unclear which one `pyaudio` will actually use.

**Root cause**: `pya.open(..., input=True, ...)` with no `input_device_index` silently falls back
to the OS default recording device (Windows Settings → Sound → Input) — whatever that happens to
be, not necessarily the one you want.

**Fix**: `list_audio_devices.py` enumerates every input/output-capable device with its index and
name. Pick the index you want, set it in `.env` as `INPUT_DEVICE_INDEX` (and `OUTPUT_DEVICE_INDEX`
for the speaker side), and `main.py` reads both and passes them explicitly to `pya.open(...)`.

## 3. Bluetooth headset: worked once, then mic stopped registering entirely

**Symptom**: first exchange worked fine (voice in, voice reply out), but every subsequent attempt
to speak went completely unregistered — no error, no crash, just silence.

**Initial (wrong) assumption**: thought it might be the code's fault. It wasn't — this specific
symptom was actually caused by **issue #4 below**, which looks identical and was only
disambiguated by adding diagnostic logging (see "Debugging method" at the bottom).

**Real, separate, genuine Bluetooth issue** (worth keeping in mind even though it wasn't the root
cause here): a Bluetooth headset normally runs in a high-quality, **output-only** profile (A2DP).
The moment its microphone is activated, the OS is forced to switch it into **HFP** (Hands-Free
Profile) — the only Bluetooth profile that supports a mic, capped at roughly 16kHz mono. If the
*same* Bluetooth device is also the default **output** device, you're asking it to simultaneously
run 16kHz mono input (forcing HFP) and higher-rate output (e.g. 24kHz) that HFP can't carry — the
audio session for that device can break silently when both directions are forced active at once.

**Fix (general principle, still good practice)**: if using a Bluetooth headset as the mic, route
audio *output* to a different device (e.g. built-in speakers) via `OUTPUT_DEVICE_INDEX`, so the
Bluetooth device only ever has to handle one direction.

## 4. THE actual bug: conversation died after exactly one turn, every time

**Symptom**: identical to #3 above, even *after* separating input/output onto different devices
(ruling out Bluetooth entirely) — first exchange worked, then total silence, no error.

**Diagnostic method that found it**: added lightweight heartbeat logging to both halves of the
pipeline (`send_audio_loop` prints mic peak-amplitude every ~50 chunks; `receive_loop` prints a
line for every single message received from the server). This showed:
- `[mic heartbeat]` kept printing indefinitely, with real amplitude spikes while talking — the
  mic/send side was completely healthy the whole time.
- `[recv heartbeat]` stopped dead the exact moment `turn_complete=True` appeared, and never
  printed again, even while clearly talking afterward.

That pinpointed the problem to the receive side specifically, not audio I/O at all.

**Root cause**: confirmed directly from the `google-genai` SDK source
(`google/genai/live.py`, `Session.receive()` docstring): *"The returned responses will represent a
complete model turn."* — `session.receive()` is an async generator scoped to **one turn**; it
naturally ends (via normal `StopAsyncIteration`, no exception) once that turn completes. Our
`receive_loop` called it once and iterated with a single `async for`, so the loop just ended
silently after turn 1 and the coroutine returned. Meanwhile `send_audio_loop` is an unrelated
infinite `while True` with no dependency on the receive side, so it kept running forever,
`asyncio.gather(...)` kept waiting on it, and nothing ever indicated the receive side had quietly
finished.

**Fix**: wrap the inner `async for` in an outer `while True:`, so a fresh `session.receive()` call
is made for each new turn:
```python
async def receive_loop(session, output_stream):
    while True:  # session.receive() only yields one turn at a time; re-enter it per turn
        async for response in session.receive():
            ...
```

**General lesson**: an async generator ending normally produces *no error at all* — silent
completion is easy to mistake for a hang. When a long-running async loop "just stops" with zero
error output, check whether the thing being iterated was ever documented/designed to be
re-entered, rather than assuming it's a single unbounded stream.

## 5. `google_search` is server-executed — does that mean zero visibility?

Not a bug, but a real question worth documenting the answer to: when the built-in `google_search`
tool fires, Google executes it server-side — unlike our own custom tools, we never get a
`tool_call` round-trip to inspect or control it.

**However**, confirmed directly from the SDK's own test fixtures (`tests/live/test_live_response.py`,
using real mocked wire-format JSON) and the `GroundingMetadata`/`GroundingChunk` type definitions
in `google/genai/types.py`: the response still carries `server_content.grounding_metadata`,
containing:
- `web_search_queries` — the exact queries that were run.
- `grounding_chunks[].web` — each source's `title`, `domain`, and full `uri`.
- `grounding_supports` — maps which part of the spoken response is backed by which source.

So: no control over the search itself, but full after-the-fact transparency into what was
searched and cited. Wired into `receive_loop` in `main.py` to print this whenever it's present.

## 6. Synthesized "drumroll" sound effect didn't actually sound like one

**Symptom**: `play_sound_effect("drumroll")` played something, but it sounded like intermittent
static bursts, not a drumroll.

**Root cause**: the original implementation alternated flat-volume noise bursts with noticeable
silence gaps — no amplitude shaping within each burst, so each one sounded like a buzz of static
rather than a percussive "hit."

**Fix**: added `_drum_hit()` — noise shaped with a fast exponential-decay envelope
(`volume * noise * exp(-decay * i / n)`), giving each hit a sharp attack and quick decay like a
real struck drum. Increased hit count (14 → 40) with much tighter spacing (small, slightly
shrinking gaps for an accelerating-roll feel), and replaced the plain sine-tone ending with a
louder, longer, slower-decaying noise hit to simulate a cymbal crash.

**General lesson for synthesizing percussion**: flat-volume noise alone reads as "static," not
"drum" — the envelope (attack/decay shape) is what makes noise sound percussive. Worth remembering
for any future sound effect work in this project.

## Debugging method worth reusing

When a long-running bidirectional async pipeline silently stops producing output with no error,
**add heartbeat logging to each independent leg of the pipeline separately**, before guessing at a
fix. This is what correctly distinguished "Bluetooth hardware issue" (plausible-sounding, but
wrong) from "`session.receive()` scoped to one turn" (the actual bug, confirmed from SDK source
once the logs pointed specifically at the receive side).
