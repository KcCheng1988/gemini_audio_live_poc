# PCM / Binary Audio Fundamentals

Everything needed to read or write raw-PCM audio code (like `tools.py`'s sound synthesis, or
`main.py`'s mic/speaker streaming) without guessing. Built up from first principles while
debugging this POC.

## What PCM is

PCM ("Pulse-Code Modulation") is sound represented as a plain list of numbers: sample the wave's
amplitude at a regular interval, write down each measurement as an integer, in order. No
compression, no encoding — raw numbers, which is why it's called "raw audio." This is exactly
why it's the format real-time voice APIs use: no decode step needed before you can play it or
stream it, which matters for latency.

## Sample rate

How many amplitude measurements are taken per second. Gemini Live uses **16kHz for input**
(mic → API) and **24kHz for output** (API → speaker) — different pipelines, different rates, both
have to match exactly what each side expects or audio plays at the wrong speed/pitch.

## Bits, bytes, and "16-bit audio"

- A **bit** is a 0 or 1. A **byte** is 8 bits.
- "16-bit" audio means each sample is stored in 16 bits = **2 bytes**.
- 16 bits gives 2¹⁶ = 65,536 distinct values — for signed audio, split as -32,768 to +32,767.
  More bits = more volume levels = smoother sound (16-bit is standard "CD quality").

## Hex digits, and why they map cleanly onto bits

A hex digit covers 0-15, which happens to need **exactly 4 bits** (2⁴ = 16) — a perfect
one-to-one match, which is *why* hex is the standard shorthand for binary data (decimal doesn't
divide evenly into bits; hex does).

| Decimal | Hex | Binary |
|---|---|---|
| 0-9 | 0-9 | 0000-1001 |
| 10 | A | 1010 |
| 11 | B | 1011 |
| 12 | C | 1100 |
| 13 | D | 1101 |
| 14 | E | 1110 |
| 15 | F | 1111 |

This generalizes cleanly: `bits ÷ 4` = hex digits needed, `bits ÷ 8` = bytes needed.

| Bits | Bytes | Hex digits |
|---|---|---|
| 8-bit | 1 | 2 |
| 16-bit | 2 | 4 |
| 32-bit | 4 | 8 |
| 64-bit | 8 | 16 |

A value is always padded to the **full fixed width** (`5` as a 16-bit value is `0x0005`, not
`0x5`) — the hex notation describes the full contents of a fixed-size memory slot, not just "how
big is this number."

**The `0x` prefix** just means "read what follows as hex, not decimal" — a label, not an
operation. `0x10` = 16 decimal, not ten. (Siblings: `0b` = binary, `0o` = octal.)

**Converting hex ↔ decimal** — positional notation, same idea as decimal just base 16 instead of
base 10:
```
0x1234 = 1×16³ + 2×16² + 3×16¹ + 4×16⁰ = 4096 + 512 + 48 + 4 = 4660
```
Equivalent byte-pair framing (since `0x1234` is really the two bytes `0x12` and `0x34`):
```
0x1234 = (0x12 × 256) + 0x34 = (18 × 256) + 52 = 4660
```

## Endianness — byte-level ordering, NOT digit-level

**Critical distinction that's easy to get wrong**: endianness reorders whole **bytes**, never the
individual hex digits inside a byte. `0x1234` is two bytes, `0x12` and `0x34` — each is one
indivisible unit (hex just needs 2 characters to display any single byte's value, 0-255).

- **Big-endian**: most-significant byte first → `12 34` (matches normal left-to-right reading).
- **Little-endian**: least-significant byte first → `34 12`.

"Smaller/bigger" refers to **significance** (positional weight: ×256 vs ×1 for a 2-byte number),
not the byte's raw numeric value — a low byte can still hold a large number (e.g. `0x01FF`: high
byte `0x01` is numerically small but worth ×256; low byte `0xFF` is numerically large but worth
×1; little-endian still writes the low byte, `FF`, first).

**Why endianness exists at all**: different CPU architectures independently chose different
conventions decades ago (no universal physical "correct" order), so both exist today and anything
moving multi-byte data has to declare which one it uses.

**Why little-endian for this project specifically**: it matches the native byte order of the CPU
actually processing the audio (x86, and ARM in its common configuration) — avoids a per-sample
conversion step, which matters at 16,000+ samples/second of continuous real-time audio.

**Common misconception, resolved**: "network byte order" (big-endian) applies only to specific
fields *inside* low-level protocol headers (IP addresses, ports, etc.) — handled automatically by
the OS, never touched directly. It says nothing about your own payload's byte order. Gemini's Live
API payload is little-endian PCM, sent over a WebSocket (which rides on TCP/IP) — completely
valid; the transport doesn't care about payload byte order, only the specific
protocol/format you're using does.

## Two's complement (signed vs. unsigned 16-bit)

Same 16 bits, two different reading rules — nothing changes in memory, only interpretation:

- If the leftmost (sign) bit is `0` → read exactly like unsigned: `0x0000`-`0x7FFF` → `0` to
  `32767`.
- If the leftmost bit is `1` → negative. **Signed value = unsigned value − 65536.**

```
0x8000: unsigned 32768 -> signed = 32768 - 65536 = -32768
0xFFFF: unsigned 65535 -> signed = 65535 - 65536 = -1
```

**Going the other direction** (negative decimal → bit pattern): if negative, **add 65536** first,
then convert that result to hex normally. Non-negative values need no adjustment.

```
-1000 -> +65536 -> 64536 -> 0xFC18
```

This is literally what `struct.pack("<h", n)` does internally before laying out the bytes.

Why `0xFFFF` = -1 specifically: think of an odometer wrapping around — counting down from `0x0000`
by one naturally wraps to `0xFFFF` (all 1-bits). Two's complement embraces that wraparound as the
definition of -1, because it makes addition/subtraction hardware work identically whether bits are
being treated as signed or unsigned.

This is also why our audio code scales by `32767`, not `32768`: positive values only go up to
`32767` (`0x7FFF`); negative goes one further, to `-32768` (`0x8000`) — the range isn't symmetric.

## `struct.pack` — the bridge from Python ints to raw bytes

```python
struct.pack(f"<{len(ints)}h", *ints)
```
- `<` = little-endian byte order.
- `h` = C `short` = signed 16-bit integer; a leading count (`3h`) means "repeat 3 times."
- `*ints` unpacks the list into separate positional args (`pack` wants one value per format slot).

Python integers aren't stored as fixed-width binary internally — `struct.pack` is what converts
"Python's idea of a number" into the exact byte layout external code (pyaudio, Gemini's API)
expects. `struct.unpack` does the reverse.

## Clipping vs. volume — not the same thing

`clip(s) = max(-1.0, min(1.0, s))` is a **ceiling/floor**, not a normalization — a value already
inside `[-1, 1]` passes through completely unchanged. `volume` is a genuine **amplitude-shaping**
multiplier applied *before* clipping (e.g. `0.3 × random.uniform(-1,1)` shrinks the range to
`[-0.3, 0.3]`, actually making the signal quieter, not just capping an already-loud one).

Setting volume above `1.0` doesn't error — it causes **clipping distortion**: the waveform's peaks
get flattened into a plateau instead of following their natural curve, which sounds harsh/buzzy
(this is literally how guitar fuzz/overdrive pedals work, deliberately — not inherently "wrong,"
just not what we want for a clean chime/drumroll).

## Why audio gets read in chunks (e.g. `CHUNK_SIZE = 1024`)

Audio is continuous/streaming — there's no complete clip to read all at once, so you must read
incrementally. Chunk size is a **latency vs. overhead trade-off**:

- Too small (e.g. 1 sample at a time) → overwhelming per-call overhead (16,000 calls/sec at 16kHz).
- Too large (e.g. buffer a full 2 seconds) → that much added latency before anything gets sent,
  defeating the point of "live" conversation.

`1024` samples at 16kHz = `1024/16000` = **64ms** per chunk (~15.6 reads/sec) — small enough to be
imperceptible as latency, large enough to keep overhead trivial. `1024` being a power of 2 is a
long-standing audio-programming convention (aligns well with how drivers/hardware buffer data),
not a hard requirement from Gemini's side — the API just wants a continuous PCM byte stream,
chunked however the client chooses.
