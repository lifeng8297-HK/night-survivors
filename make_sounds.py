"""Make short sound effects with only the standard library.

Run on your computer (not in a browser):  python make_sounds.py
Writes .wav files into sounds/.

A sound is a list of numbers. Each one is the air pressure at that moment,
22050 of them every second. value = sin(phase) * envelope, kept inside -1..1.
"""
import math
import os
import struct
import wave

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, "sounds")
RATE = 22050


def write_wav(name, samples):
    path = os.path.join(OUT, name + ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000)) for s in samples))
    print("sounds/%s.wav  %d numbers = %.2f s" % (name, len(samples), len(samples) / RATE))


def tone(freq_start, freq_end, seconds, decay=True):
    """A wiggle that slides from one pitch to another, fading out as it goes."""
    n = int(RATE * seconds)
    out = []
    phase = 0.0
    for i in range(n):
        phase += 2 * math.pi * (freq_start + (freq_end - freq_start) * i / n) / RATE
        envelope = 1 - i / n if decay else 1.0
        out.append(math.sin(phase) * envelope)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    write_wav("shoot", tone(1400, 700, 0.06))       # a bright blip: the wand fired
    write_wav("hit", tone(700, 300, 0.08))          # a short fall: something was hit
    write_wav("gem", tone(900, 1500, 0.12))         # a rise: a crystal picked up
    write_wav("levelup", tone(400, 1200, 0.35))     # a long rise: level up
    write_wav("hurt", tone(300, 90, 0.25))          # low and rough: you lost HP
    write_wav("end", tone(500, 60, 0.9))            # a long slide down: the run is over


if __name__ == "__main__":
    main()
