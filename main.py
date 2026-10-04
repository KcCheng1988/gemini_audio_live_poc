import asyncio
import os
import struct

import pyaudio
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import FUNCTION_DECLARATIONS, OUTPUT_SAMPLE_RATE, play_sound_effect, set_mood_light

load_dotenv()

MODEL = "gemini-3.8-live"
INPUT_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

SYSTEM_INSTRUCTION = (
    "You are a helpful, friendly voice assistant for general questions. "
    "Use google_search when you need up-to-date or factual information you're "
    "not sure about. You also control mood lighting and can play sound effects "
    "when it fits the conversation (e.g. play a success chime after good news, "
    "or a drumroll before a fun reveal) — use these tools playfully but not "
    "constantly."
)

CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_INSTRUCTION,
    "input_audio_transcription": {},
    "output_audio_transcription": {},
    "tools": [
        {"google_search": {}},
        {"function_declarations": FUNCTION_DECLARATIONS},
    ],
}


async def send_audio_loop(session, input_stream):
    chunk_count = 0
    while True:
        chunk = await asyncio.to_thread(
            input_stream.read, CHUNK_SIZE, False  # exception_on_overflow=False
        )
        chunk_count += 1
        if chunk_count % 50 == 0:  # roughly every ~3 seconds
            samples = struct.unpack(f"<{len(chunk) // 2}h", chunk)
            peak = max(abs(s) for s in samples)
            print(f"[mic heartbeat] chunk #{chunk_count}, peak amplitude: {peak} (quiet if < ~500)")

        await session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
        )


async def handle_tool_call(session, output_stream, tool_call):
    function_responses = []
    for fc in tool_call.function_calls:
        print(f"[model called tool] {fc.name}({dict(fc.args)})")

        if fc.name == "set_mood_light":
            result = set_mood_light(**fc.args)
        elif fc.name == "play_sound_effect":
            result = await asyncio.to_thread(play_sound_effect, output_stream=output_stream, **fc.args)
        else:
            result = {"status": "error", "message": f"Unknown tool '{fc.name}'"}

        function_responses.append(
            types.FunctionResponse(id=fc.id, name=fc.name, response=result)
        )

    await session.send_tool_response(function_responses=function_responses)


async def receive_loop(session, output_stream):
    response_count = 0
    while True:  # session.receive() only yields one turn at a time; re-enter it per turn
        async for response in session.receive():
            response_count += 1
            server_content = response.server_content
            print(
                f"[recv heartbeat] response #{response_count}, "
                f"has_server_content={bool(server_content)}, "
                f"turn_complete={getattr(server_content, 'turn_complete', None)}, "
                f"has_tool_call={bool(response.tool_call)}"
            )

            if server_content:
                if server_content.input_transcription and server_content.input_transcription.text:
                    print(f"You: {server_content.input_transcription.text}")

                if server_content.output_transcription and server_content.output_transcription.text:
                    print(f"Assistant: {server_content.output_transcription.text}")

                if server_content.grounding_metadata:
                    gm = server_content.grounding_metadata
                    if gm.web_search_queries:
                        print(f"[google_search] queries: {gm.web_search_queries}")
                    if gm.grounding_chunks:
                        for chunk in gm.grounding_chunks:
                            if chunk.web:
                                print(f"[google_search] source: {chunk.web.title} - {chunk.web.uri}")

                if server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.inline_data:
                            await asyncio.to_thread(output_stream.write, part.inline_data.data)

            if response.tool_call:
                await handle_tool_call(session, output_stream, response.tool_call)


async def main():
    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)

    input_device_index = os.environ.get("INPUT_DEVICE_INDEX")
    if input_device_index is not None:
        input_device_index = int(input_device_index)

    output_device_index = os.environ.get("OUTPUT_DEVICE_INDEX")
    if output_device_index is not None:
        output_device_index = int(output_device_index)

    pya = pyaudio.PyAudio()
    if input_device_index is not None:
        device_name = pya.get_device_info_by_index(input_device_index)["name"]
        print(f"Using input device {input_device_index}: {device_name}")
    if output_device_index is not None:
        device_name = pya.get_device_info_by_index(output_device_index)["name"]
        print(f"Using output device {output_device_index}: {device_name}")

    input_stream = pya.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=INPUT_SAMPLE_RATE,
        input=True,
        input_device_index=input_device_index,
        frames_per_buffer=CHUNK_SIZE,
    )
    output_stream = pya.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=OUTPUT_SAMPLE_RATE,
        output_device_index=output_device_index,
        output=True,
    )

    print("Connecting to Gemini Live...")
    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        print("Connected. Start talking (Ctrl+C to stop).")
        try:
            await asyncio.gather(
                send_audio_loop(session, input_stream),
                receive_loop(session, output_stream),
            )
        except KeyboardInterrupt:
            pass
        finally:
            input_stream.close()
            output_stream.close()
            pya.terminate()


if __name__ == "__main__":
    asyncio.run(main())
