import math
import random
import struct

OUTPUT_SAMPLE_RATE = 24000  # must match the Live API's audio output rate


def _pcm_bytes(samples: list[float]) -> bytes:
    clipped = [max(-1.0, min(1.0, s)) for s in samples]
    ints = [int(s * 32767) for s in clipped]
    return struct.pack(f"<{len(ints)}h", *ints)


def _tone(freq: float, duration_s: float, volume: float = 0.5) -> list[float]:
    n = int(OUTPUT_SAMPLE_RATE * duration_s)
    return [
        volume * math.sin(2 * math.pi * freq * (i / OUTPUT_SAMPLE_RATE))
        for i in range(n)
    ]


def _silence(duration_s: float) -> list[float]:
    return [0.0] * int(OUTPUT_SAMPLE_RATE * duration_s)


def _noise_burst(duration_s: float, volume: float = 0.3) -> list[float]:
    n = int(OUTPUT_SAMPLE_RATE * duration_s)
    return [volume * random.uniform(-1.0, 1.0) for _ in range(n)]


def _build_success_chime() -> bytes:
    samples = _tone(523.25, 0.12) + _silence(0.02) + _tone(783.99, 0.18)
    return _pcm_bytes(samples)


def _drum_hit(duration_s: float, volume: float = 0.6, decay: float = 6.0) -> list[float]:
    """A single percussive hit: noise shaped with a fast exponential decay,
    so it sounds like a struck drum instead of a flat buzz of static."""
    raw = _noise_burst(duration_s, volume=1.0)
    n = len(raw)
    return [volume * s * math.exp(-decay * i / max(n - 1, 1)) for i, s in enumerate(raw)]


def _build_drumroll() -> bytes:
    samples: list[float] = []
    num_hits = 40
    for i in range(num_hits):
        samples += _drum_hit(duration_s=0.02, volume=0.5)
        gap = max(0.004, 0.018 - i * 0.0003)  # hits tighten up -> accelerating roll
        samples += _silence(gap)
    samples += _drum_hit(duration_s=0.3, volume=0.9, decay=4.0)  # final crash
    return _pcm_bytes(samples)


SOUND_EFFECTS: dict[str, bytes] = {
    "success_chime": _build_success_chime(),
    "drumroll": _build_drumroll(),
}


# Mock state, just so set_mood_light has something to report back / be asked about.
_mood_light_state = {"color": "warm white"}


def set_mood_light(color: str) -> dict:
    _mood_light_state["color"] = color
    print(f"[tool] mood light set to: {color}")
    return {"status": "ok", "color": color}


def play_sound_effect(effect_name: str, output_stream) -> dict:
    data = SOUND_EFFECTS.get(effect_name)
    if data is None:
        return {
            "status": "error",
            "message": f"Unknown effect '{effect_name}'. Available: {list(SOUND_EFFECTS)}",
        }
    print(f"[tool] playing sound effect: {effect_name}")
    output_stream.write(data)
    return {"status": "ok", "effect_name": effect_name}


FUNCTION_DECLARATIONS = [
    {
        "name": "set_mood_light",
        "description": "Set the mood lighting in the room to a given color.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "color": {
                    "type": "STRING",
                    "description": "The color to set the lights to, e.g. 'blue', 'warm white', 'red'.",
                }
            },
            "required": ["color"],
        },
    },
    {
        "name": "play_sound_effect",
        "description": "Play a short sound effect out loud.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "effect_name": {
                    "type": "STRING",
                    "description": "Which effect to play.",
                    "enum": list(SOUND_EFFECTS),
                }
            },
            "required": ["effect_name"],
        },
    },
]
