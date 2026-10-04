import pyaudio

pya = pyaudio.PyAudio()

default_input = pya.get_default_input_device_info()
print(f"Current OS default input device: index {default_input['index']} - {default_input['name']}")
default_output = pya.get_default_output_device_info()
print(f"Current OS default output device: index {default_output['index']} - {default_output['name']}")
print()

print("All input-capable devices:")
for i in range(pya.get_device_count()):
    info = pya.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        print(f"  index {i}: {info['name']}  (channels={info['maxInputChannels']}, default_rate={int(info['defaultSampleRate'])})")

print()
print("All output-capable devices:")
for i in range(pya.get_device_count()):
    info = pya.get_device_info_by_index(i)
    if info["maxOutputChannels"] > 0:
        print(f"  index {i}: {info['name']}  (channels={info['maxOutputChannels']}, default_rate={int(info['defaultSampleRate'])})")

pya.terminate()
