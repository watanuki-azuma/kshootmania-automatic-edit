"""Evaluate BPM / offset detection against the official corpus charts.

Usage: uv run python tests/eval/eval_analyze.py [song_dir ...]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from ksmauto.analyze import analyze

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus" / "official"


def header(ksh: Path) -> dict[str, str]:
    out = {}
    for line in ksh.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if line.strip() == "--":
            break
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v.strip()
    return out


def circ_err(x: float, period: float) -> float:
    d = x % period
    return min(d, period - d)


def main() -> None:
    dirs = [Path(d) for d in sys.argv[1:]] or sorted(p.parent for p in CORPUS.glob("*/*/*.ogg"))
    ok_bpm = ok_phase = 0
    for d in dirs:
        ksh = sorted(d.glob("*.ksh"))[0]
        h = header(ksh)
        gt_bpm = float(h["t"])
        gt_off = float(h.get("o", "0"))
        audio = d / h["m"].split(";")[0]
        t0 = time.time()
        a = analyze(audio)
        bpm = a["tempo"]["bpm"]
        beat_ms = 60000.0 / gt_bpm
        pe = circ_err(a["offset_ms"] - gt_off, beat_ms)
        me = circ_err(a["offset_ms"] - gt_off, beat_ms * 4)
        b_ok = abs(bpm - gt_bpm) <= 0.5
        p_ok = b_ok and pe <= 15
        ok_bpm += b_ok
        ok_phase += p_ok
        print(f"{d.name:<26} gt {gt_bpm:>6g}  est {bpm:>7g} {'OK' if b_ok else 'NG'}  "
              f"off {a['offset_ms']:>5}  beat-phase err {pe:5.1f}ms {'OK' if p_ok else 'NG'}  "
              f"bar-phase err {me:6.1f}ms  cands {a['tempo']['candidates'][:3]}  {time.time() - t0:.1f}s")
    print(f"BPM {ok_bpm}/{len(dirs)}  beat phase {ok_phase}/{len(dirs)}")


if __name__ == "__main__":
    main()
