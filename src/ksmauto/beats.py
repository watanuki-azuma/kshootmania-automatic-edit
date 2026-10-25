"""Track beats/downbeats with Beat This! and suggest a measure tempo map."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from bisect import bisect_left
from pathlib import Path
from statistics import median


def fold_bpm(bpm: float, min_bpm: float = 120, max_bpm: float = 240) -> float:
    """Choose the octave of `bpm` in [min_bpm, max_bpm)."""
    if not (math.isfinite(bpm) and bpm > 0 and math.isfinite(min_bpm) and math.isfinite(max_bpm) and 0 < min_bpm < max_bpm):
        raise ValueError("BPM and bounds must be positive and finite")
    while bpm < min_bpm:
        bpm *= 2
    while bpm >= max_bpm:
        bpm /= 2
    if bpm < min_bpm:
        raise ValueError("BPM range contains no octave of the detected tempo")
    return bpm


def _round_bpm(bpm: float) -> float:
    for step, tol in ((1, 0.2), (0.5, 0.1)):
        if abs(bpm - round(bpm / step) * step) <= tol:
            return round(bpm / step) * step
    return round(bpm, 1)


def _fit(times: list[float], period: float) -> tuple[float, float, list[float], float, list[float]]:
    """Index beats in steps of `period` from the previous kept beat, skipping off-grid
    ones, then least-squares fit. Eight or more off-grid beats at the end (a phase jump)
    are returned unfitted. Returns (time of index 0, period, kept times, max residual, rest)."""
    pts, last = [(0, times[0])], 0
    for i, t in enumerate(times[1:], 1):
        x = (t - pts[-1][1]) / period
        if round(x) and abs(x - round(x)) <= 0.25:
            pts.append((pts[-1][0] + round(x), t))
            last = i
    rest = times[last + 1:] if len(times) - last > 8 else []
    for _ in range(2):  # refit without the beats the first line leaves off the grid
        n_mean = sum(n for n, _ in pts) / len(pts)
        t_mean = sum(t for _, t in pts) / len(pts)
        var = sum((n - n_mean) ** 2 for n, _ in pts)
        slope = sum((n - n_mean) * (t - t_mean) for n, t in pts) / var if var else period
        t0 = t_mean - slope * n_mean
        pts = [(n, t) for n, t in pts if abs(t - t0 - n * slope) <= 0.1 * slope] or pts
    return t0, slope, [t for _, t in pts], max(abs(t - t0 - n * slope) for n, t in pts), rest


def _segment(times: list[float], period: float, downbeats: list[float]) -> dict:
    t0, period, kept, resid, rest = _fit(times, period)
    inside = [d for d in downbeats if kept[0] - period / 2 <= d <= kept[-1] + period / 2]
    xs = [(d - t0) / period for d in inside]
    pos = [round(x) for x in xs if abs(x - round(x)) <= 0.25]
    gaps = [b - a for a, b in zip(pos, pos[1:]) if b > a]
    meter = max(set(gaps), key=gaps.count) if gaps else 4
    while meter > 6 and meter % 2 == 0:  # downbeats every other bar at half tempo
        meter //= 2
    phase = max(set(p % meter for p in pos), key=[p % meter for p in pos].count) if pos else 0
    return {"t0": t0, "period": period, "kept": kept, "resid": resid, "rest": rest, "meter": meter,
            "grid": t0 + phase * period, "gaps": gaps}


def tempo_map(beats: list[float], downbeats: list[float], min_bpm: float = 120,
              max_bpm: float = 240) -> dict:
    """Fit beat runs of steady tempo, fold octaves into [min_bpm, max_bpm), and number
    measures by elapsed time so ignored unstable stretches do not shift later bars.

    Times remain raw model seconds. Meter changes are reported, not applied by analyze.
    """
    if not (math.isfinite(min_bpm) and math.isfinite(max_bpm) and 0 < min_bpm < max_bpm):
        raise ValueError("BPM bounds must be finite, positive and increasing")
    beats, downbeats = list(map(float, beats)), list(map(float, downbeats))
    for times in (beats, downbeats):
        if any(not math.isfinite(t) or t < 0 for t in times) or any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError("beat times must be finite, nonnegative and strictly increasing")
    if len(downbeats) < 3 or len(beats) < 9:
        raise ValueError("at least three downbeats and nine beats are needed")
    warnings = []
    ibi = [b - a for a, b in zip(beats, beats[1:])]
    # The window median survives a stray or missing beat.
    local = [median(ibi[max(0, i - 4):i + 5]) for i in range(len(ibi))]
    groups = []
    for i, p in enumerate(local):
        if groups and abs(p / median(local[j] for j in groups[-1]) - 1) <= 0.03:
            groups[-1].append(i)
        else:
            groups.append([i])
    segs = []
    for g in (g for g in groups if len(g) >= 8):
        tracked = median(local[j] for j in g)
        factor = 2 ** round(math.log2(fold_bpm(60 / tracked, min_bpm, max_bpm) * tracked / 60))
        long = [beats[j] for j in g[:-2] if all(ibi[k] > 1.5 * tracked for k in (j, j + 1, j + 2))]
        times = beats[g[0]:g[-1] + 2]
        while len(times) >= 9:
            seg = _segment(times, tracked / factor, downbeats)
            times = seg["rest"]
            seg["factor"] = factor
            # A lone long gap is a missed beat; a run of them is a held note or rest.
            if any(seg["kept"][0] <= t <= seg["kept"][-1] for t in long):
                seg["break"] = next(t for t in long if t >= seg["kept"][0])
            prev = segs[-1] if segs else None
            if prev and prev["meter"] == seg["meter"] and abs(prev["period"] / seg["period"] - 1) <= 0.02:
                merged = _segment(prev["kept"] + seg["kept"], prev["period"], downbeats)
                if not merged["rest"] and len(merged["kept"]) >= 0.9 * (len(prev["kept"]) + len(seg["kept"])):
                    merged["factor"] = prev["factor"] if prev["factor"] != 1 else factor
                    if "break" in prev or "break" in seg:
                        merged["break"] = prev.get("break", seg.get("break"))
                    segs[-1] = merged
                    continue
            segs.append(seg)
    if not segs:
        raise ValueError("no stretch of steady beats (two bars or more) was found")
    segments = []
    for i, seg in enumerate(segs):
        bar = seg["meter"] * seg["period"]
        if i == 0:
            m, start = 0, seg["grid"] - math.floor((seg["grid"] - seg["kept"][0]) / bar + 0.5) * bar
            offset = start
        else:
            prev, (pm, pstart, pbar) = segs[i - 1], last
            # The change lies between the last beat on the old grid and the first on the new.
            lo = max(1, math.ceil((prev["kept"][-1] - pstart) / pbar - 0.3))
            hi = max(lo, math.floor((seg["kept"][0] - pstart) / pbar + 0.3))

            def miss(k):
                x = (seg["grid"] - pstart - k * pbar) / bar
                return abs(x - round(x))
            k = min(range(lo, hi + 1), key=lambda k: (round(miss(k), 2), k))
            m, start = pm + k, pstart + k * pbar
            if miss(k) > 0.05:
                warnings.append(f"m{m}: the new beat grid is {miss(k) * bar * 1000:.0f} ms off the old bar line; "
                                "verify the change by ear.")
            if seg["kept"][0] - prev["kept"][-1] > 2 * pbar:
                warnings.append(f"{prev['kept'][-1]:.1f}-{seg['kept'][0]:.1f}s: unstable beats ignored; "
                                f"tempo change placed at m{m}, verify by ear.")
        last = (m, start, bar)
        bpm = _round_bpm(60 / seg["period"])
        if segments and seg["meter"] != segments[-1][2]:
            warnings.append(f"m{m}: time signature may change to {seg['meter']}/4; reported only, verify manually.")
        if seg["factor"] != 1:
            warnings.append(f"m{m}: beats tracked at an octave of {bpm:g} BPM (x{seg['factor']:g}); "
                            "measures counted at the folded tempo.")
        if "break" in seg:
            warnings.append(f"m{m + math.floor((seg['break'] - start) / bar)}: long gap between beats (fermata or break) "
                            "absorbed into the grid; verify timing manually.")
        odd = [a for a, b in zip(seg["gaps"], seg["gaps"][1:]) if a == b and a % seg["meter"]]
        if odd:
            warnings.append(f"m{m}-: some bars have {odd[0]} beats; time signature may change, verify manually.")
        segments.append([m, bpm, seg["meter"]])
    bars = [60 * (bisect_left(beats, e - 1e-6) - bisect_left(beats, s - 1e-6)) / (e - s)
            for s, e in zip(downbeats, downbeats[1:])]
    for i in range(len(bars) - 3):
        steps = [bars[j + 1] / bars[j] - 1 for j in range(i, i + 3) if bars[j]]
        if len(steps) == 3 and all(0.003 < abs(s) < 0.1 for s in steps) and (all(s > 0 for s in steps) or all(s < 0 for s in steps)):
            warnings.append("Gradual tempo drift (ritardando or accelerando); verify timing manually.")
            break
    return {"beats": beats, "downbeats": downbeats, "offset_ms": round(offset * 1000),
            "segments": segments, "tempo_arg": ",".join(f"{m}:{b:g}" for m, b, _ in segments),
            "warnings": warnings}


def track(audio: str | Path, model: str = "final0", min_bpm: float = 120, max_bpm: float = 240) -> dict:
    from beat_this.inference import File2Beats

    beats, downbeats = File2Beats(checkpoint_path=model, device="cpu", dbn=False)(str(audio))
    return tempo_map(beats.tolist(), downbeats.tolist(), min_bpm, max_bpm)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto beats", description=__doc__)
    p.add_argument("audio")
    p.add_argument("-o", "--output", required=True, type=Path)
    p.add_argument("--model", choices=("final0", "small0"), default="final0")
    p.add_argument("--min-bpm", type=float, default=120)
    p.add_argument("--max-bpm", type=float, default=240)
    args = p.parse_args(argv)
    if importlib.util.find_spec("beat_this") is None:
        print("beat-this is not installed: uv sync --extra beats", file=sys.stderr)
        return 1
    try:
        result = track(args.audio, args.model, args.min_bpm, args.max_bpm)
        args.output.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{len(result['beats'])} beats, {len(result['downbeats'])} downbeats: {args.output}")
    print(f"analyze arguments: --tempo {result['tempo_arg']} --offset {result['offset_ms']}")
    for warning in result["warnings"]:
        print(f"warning: {warning}")
    return 0
