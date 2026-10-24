"""Transcribe a piano stem into notes with ByteDance's piano transcription model.

The model (piano_transcription_inference, PyTorch; Apache-2.0) is not a dependency
of ksmauto: install it with the `transcribe` extra, or point `--python` at an
interpreter that has it. The first run downloads the ~170 MB checkpoint to
~/piano_transcription_inference_data/.
The notes feed `ksmauto analyze --stems DIR` as DIR/<stem>.notes.json.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Runs in the interpreter that has the model; writes [[onset s, offset s, midi, velocity 0-1], ...].
_SCRIPT = """
import json, sys, librosa
from piano_transcription_inference import PianoTranscription, sample_rate
y, _ = librosa.load(sys.argv[1], sr=sample_rate, mono=True)
events = PianoTranscription(device="cpu").transcribe(y, sys.argv[3])["est_note_events"]
notes = sorted([round(float(n["onset_time"]), 4), round(float(n["offset_time"]), 4), int(n["midi_note"]),
                round(int(n["velocity"]) / 127, 3)] for n in events)
json.dump(notes, open(sys.argv[2], "w"))
"""


def transcribe(audio: str | Path, out: str | Path | None = None, python: str | None = None) -> Path:
    """Write the notes of `audio` to `out` (default: <audio stem>.notes.json beside it)."""
    audio = Path(audio)
    out = Path(out) if out else audio.with_suffix(".notes.json")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([python or sys.executable, "-c", _SCRIPT, str(audio), str(out), str(Path(tmp) / "notes.mid")],
                       check=True)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto transcribe", description=__doc__.splitlines()[0])
    p.add_argument("audio", help="piano stem (e.g. stems/piano.wav from `separate --model htdemucs_6s`)")
    p.add_argument("-o", "--output", help="notes JSON (default: <audio>.notes.json)")
    p.add_argument("--python", help="interpreter with piano_transcription_inference installed (default: this one)")
    args = p.parse_args(argv)
    if not args.python and importlib.util.find_spec("piano_transcription_inference") is None:
        print("piano_transcription_inference is not installed: uv sync --extra transcribe (or pass --python)",
              file=sys.stderr)
        return 1
    out = transcribe(args.audio, args.output, args.python)
    print(f"{len(json.loads(out.read_text()))} notes: {out}")
    return 0
