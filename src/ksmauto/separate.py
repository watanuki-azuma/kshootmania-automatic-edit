"""Split a song into vocals / drums / bass / other stems with Demucs.

Demucs (and PyTorch) are not dependencies of ksmauto: install them with the
`stems` extra, or point `--python` at an interpreter that has them.
`--model htdemucs_6s` also splits piano and guitar out of "other" (the piano stem
can then be transcribed with `ksmauto transcribe`).
The stems feed `ksmauto analyze --stems DIR`.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STEMS = ("vocals", "drums", "bass", "other")
MODELS = {"htdemucs": STEMS, "htdemucs_6s": STEMS + ("piano", "guitar")}
MODEL = "htdemucs"


def separate(audio: str | Path, out_dir: str | Path, python: str | None = None, model: str = MODEL) -> dict[str, Path]:
    """Write <out_dir>/{vocals,drums,bass,other[,piano,guitar]}.wav and return their paths."""
    audio, out_dir = Path(audio), Path(out_dir)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([python or sys.executable, "-m", "demucs", "-n", model, "-o", tmp, str(audio)],
                       check=True)
        src = Path(tmp) / model / audio.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        # Stems and transcriptions left from an earlier run would be read as this song's.
        for name in set(MODELS["htdemucs_6s"]) - set(MODELS[model]):
            (out_dir / f"{name}.wav").unlink(missing_ok=True)
        for path in out_dir.glob("*.notes.json"):
            path.unlink()
        paths = {}
        for name in MODELS[model]:
            paths[name] = out_dir / f"{name}.wav"
            shutil.move(src / f"{name}.wav", paths[name])
    return paths


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto separate", description=__doc__.splitlines()[0])
    p.add_argument("audio")
    p.add_argument("-o", "--output", required=True, help="directory for the stem WAV files")
    p.add_argument("--python", help="interpreter with demucs installed (default: this one)")
    p.add_argument("--model", choices=sorted(MODELS), default=MODEL,
                   help="htdemucs_6s also writes piano.wav and guitar.wav")
    args = p.parse_args(argv)
    if not args.python and importlib.util.find_spec("demucs") is None:
        print("demucs is not installed: uv sync --extra stems (or pass --python)", file=sys.stderr)
        return 1
    for name, path in separate(args.audio, args.output, args.python, args.model).items():
        print(f"{name}: {path}")
    return 0
