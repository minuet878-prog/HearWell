"""Generate the hearing loss simulator's four sentences with Google Cloud Text-to-Speech (#486).

Development-only tool; uses the standard library, so nothing is added to any requirements file.
The owner runs it with their own Google Cloud project; the key is read from the environment and
never written anywhere.

1. In the Google Cloud console, enable the Cloud Text-to-Speech API and create an API key
   restricted to that API.
2. From the repository root run (the folder must not exist yet; it is outside the repository):
       read -s GOOGLE_TTS_API_KEY && export GOOGLE_TTS_API_KEY
       python -I scripts/make_simulator_speech.py ~/Desktop/simulator-speech
3. It writes one WAV per sentence and voice: the female sentences with cmn-TW-Wavenet-A, the male
   ones with both cmn-TW-Wavenet-B and cmn-TW-Wavenet-C so the owner can pick by ear.

Settings (docs/planning/redesign/simulator-audio.md): Mandarin (Taiwan), WaveNet, LINEAR16 at
24 kHz mono, speaking rate 1.0. 24 kHz keeps the 8000 Hz band the simulator filters.
"""

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
FEMALE = ("cmn-TW-Wavenet-A",)
MALE = ("cmn-TW-Wavenet-B", "cmn-TW-Wavenet-C")
# The sentences the owner approved for #485, in order (phase-3-grill-decisions.md).
SENTENCES = (
    ("1", "星期四下午三點去看醫生。", FEMALE),
    ("2", "這個藥飯後吃，一天三次。", MALE),
    ("3", "孫子說下禮拜六要回來吃飯。", FEMALE),
    ("4", "謝謝你送的水果，很新鮮。", MALE),
)


def synthesize(key, text, voice):
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "cmn-TW", "name": voice},
        "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000, "speakingRate": 1.0},
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
    )
    with urllib.request.urlopen(request) as response:
        return base64.b64decode(json.load(response)["audioContent"])


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python -I scripts/make_simulator_speech.py <new output folder>")
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        sys.exit("Set GOOGLE_TTS_API_KEY first (see the top of this file).")
    out = Path(sys.argv[1]).expanduser()
    out.mkdir(parents=True)
    for number, text, voices in SENTENCES:
        for voice in voices:
            path = out / f"{number}-{voice}.wav"
            path.write_bytes(synthesize(key, text, voice))
            print(path)


if __name__ == "__main__":
    main()
