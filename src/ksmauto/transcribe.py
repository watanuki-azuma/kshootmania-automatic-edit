"""Transcribe audio into notes with ByteDance or MuScriptor.

The model (piano_transcription_inference, PyTorch; Apache-2.0) is not a dependency
of ksmauto: install it with the `transcribe` extra, or point `--python` at an
interpreter that has it. The first run downloads the ~170 MB checkpoint to
~/piano_transcription_inference_data/.
MuScriptor transcribes a mix into per-instrument notes. Install it in a separate
Python 3.12 environment and pass `--python`; its gated, non-commercial weights
require Hugging Face license acceptance and HF_TOKEN.
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

# MuScriptor instrument groups -> stem rows (drums are left to the drum stem).
MUSCRIPTOR_ROWS = {"acoustic_piano": "piano", "electric_piano": "piano",
                   "acoustic_guitar": "guitar", "clean_electric_guitar": "guitar",
                   "distorted_electric_guitar": "guitar", "acoustic_bass": "bass", "electric_bass": "bass",
                   "voice": "vocal", "drums": None}


def _write_muscriptor_notes(events: list, out: Path) -> list[Path]:
    """Write MuScriptor's JSON events (note starts and ends) as <out>/<row>.notes.json."""
    starts = {e["index"]: e for e in events if e["type"] == "start"}
    rows = {}
    for e in events:
        if e["type"] != "end" or e["start_event_index"] not in starts:
            continue
        start = starts[e["start_event_index"]]
        row = MUSCRIPTOR_ROWS.get(start["instrument"], "other")
        if row:
            # MuScriptor has no velocity.
            rows.setdefault(row, []).append([round(start["start_time"], 4), round(e["end_time"], 4),
                                             int(start["pitch"]), 1.0])
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for row, notes in sorted(rows.items()):
        path = out / f"{row}.notes.json"
        path.write_text(json.dumps(sorted(notes)), encoding="utf-8")
        paths.append(path)
    return paths


def transcribe(audio: str | Path, out: str | Path | None = None, python: str | None = None) -> Path:
    """Write the notes of `audio` to `out` (default: <audio stem>.notes.json beside it)."""
    audio = Path(audio)
    out = Path(out) if out else audio.with_suffix(".notes.json")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([python or sys.executable, "-c", _SCRIPT, str(audio), str(out), str(Path(tmp) / "notes.mid")],
                       check=True)
    return out


def transcribe_muscriptor(audio: str | Path, out: str | Path | None = None, python: str | None = None,
                         model: str = "small") -> list[Path]:
    """Transcribe a mix to <out>/<row>.notes.json (default: beside the audio)."""
    audio = Path(audio)
    out = Path(out) if out else audio.parent
    python = python or sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        events = Path(tmp) / "events.json"
        # JSON events keep the audio's seconds (no beat alignment as in its MIDI output).
        subprocess.run([python, "-m", "muscriptor", "transcribe", "--model", model, "--format", "json",
                        str(audio), "-o", str(events)], check=True)
        return _write_muscriptor_notes(json.loads(events.read_text()), out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto transcribe", description=__doc__.splitlines()[0])
    p.add_argument("audio", help="piano stem (bytedance) or mix (muscriptor)")
    p.add_argument("--engine", choices=("bytedance", "muscriptor"), default="bytedance")
    p.add_argument("--model", choices=("small", "medium", "large"), default="small",
                   help="MuScriptor model (default: small, suitable for CPU)")
    p.add_argument("-o", "--output", help="notes JSON (bytedance) or directory (muscriptor); default: beside audio")
    p.add_argument("--python", help="interpreter with the selected engine installed (default: this one)")
    args = p.parse_args(argv)
    if args.engine == "muscriptor":
        if not args.python and importlib.util.find_spec("muscriptor") is None:
            print("muscriptor is not installed: install muscriptor>=0.4 in a Python 3.12 venv and pass --python",
                  file=sys.stderr)
            return 1
        paths = transcribe_muscriptor(args.audio, args.output, args.python, args.model)
        for path in paths:
            print(f"{len(json.loads(path.read_text()))} notes: {path}")
        return 0
    if not args.python and importlib.util.find_spec("piano_transcription_inference") is None:
        print("piano_transcription_inference is not installed: uv sync --extra transcribe (or pass --python)",
              file=sys.stderr)
        return 1
    out = transcribe(args.audio, args.output, args.python)
    print(f"{len(json.loads(out.read_text()))} notes: {out}")
    return 0
