"""Split a song into vocals / drums / bass / other stems with Demucs.

Demucs (and PyTorch) are not dependencies of ksmauto: install them with the
`stems` extra, or point `--python` at an interpreter that has them.
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
MODEL = "htdemucs"


def separate(audio: str | Path, out_dir: str | Path, python: str | None = None) -> dict[str, Path]:
    """Write <out_dir>/{vocals,drums,bass,other}.wav and return their paths."""
    audio, out_dir = Path(audio), Path(out_dir)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([python or sys.executable, "-m", "demucs", "-n", MODEL, "-o", tmp, str(audio)],
                       check=True)
        src = Path(tmp) / MODEL / audio.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name in STEMS:
            paths[name] = out_dir / f"{name}.wav"
            shutil.move(src / f"{name}.wav", paths[name])
    return paths


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto separate", description=__doc__.splitlines()[0])
    p.add_argument("audio")
    p.add_argument("-o", "--output", required=True, help="directory for the stem WAV files")
    p.add_argument("--python", help="interpreter with demucs installed (default: this one)")
    args = p.parse_args(argv)
    if not args.python and importlib.util.find_spec("demucs") is None:
        print("demucs is not installed: uv sync --extra stems (or pass --python)", file=sys.stderr)
        return 1
    for name, path in separate(args.audio, args.output, args.python).items():
        print(f"{name}: {path}")
    return 0
