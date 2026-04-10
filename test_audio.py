from core.audio.lsb import AudioLSBEncoder
from core.crypto import aes
from core.audio._convert import encode_wav_to_format, decode_audio_to_wav
import os

encoder = AudioLSBEncoder()
os.system("echo 'hello world' > secret.txt")
secret = aes.encrypt(b"hello world", "testkey")

# We need a carrier
# Creating a dummy valid WAV file...
import wave, struct
with wave.open("dummy.wav", "w") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(44100)
    for _ in range(44100):
        f.writeframes(struct.pack('h', 0))

carrier = open("dummy.wav", "rb").read()

# Encode
stego_bytes = encoder.encode(carrier, secret, depth=1)

# Now, write it as MP3!
open("stego.mp3", "wb").write(stego_bytes)

# Try detection logic
stego_read = open("stego.mp3", "rb").read()

for m in ["audio-lsb", "phase"]:
    from cli import get_encoder
    enc = get_encoder(m)
    try:
        raw = enc.decode(stego_read, ext=".mp3", depth=1)
        if raw.startswith(b"SFRG"):
            print("DETECTED with", m)
    except Exception as e:
        print("Failed", m, e)

