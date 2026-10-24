"""Playability lint and density statistics for KSON charts."""

from __future__ import annotations

import math

from dataclasses import dataclass
from fractions import Fraction

from .timing import TimingMap

LANES = ["A", "B", "C", "D"]
FX_LANES = ["L", "R"]

JACK_MIN_SEC = 0.075         # same-lane repeats faster than this are hard to hit cleanly
SHORT_LONG_BEATS = Fraction(1, 8)
MAX_PEAK_WINDOW_SEC = 2.0
# K-Shoot MANIA v2 (Judgment/JudgmentDefines.hpp): from this BPM, holds and lasers tick
# every 8th instead of every 16th.
HALVE_CHAIN_BPM = 256.0


@dataclass
class Finding:
    level: str      # "warning" | "info"
    rule: str
    where: str      # "m12:1/2"
    message: str


def _notes(lane):
    for note in lane:
        yield (note, 0) if isinstance(note, int) else (note[0], note[1])


def _value(v):
    return (v, v) if not isinstance(v, list) else (v[0], v[1])


def _where(timing: TimingMap, chart: dict, y: int) -> str:
    m, off = timing.pulse_to_measure(y)
    den = _sig(chart, m)[1]
    beat = Fraction(int(round(off)), 960 // den)
    return f"m{m}:{_fmt(beat)}"


def _fmt(b: Fraction) -> str:
    if b.denominator == 1:
        return str(b.numerator)
    whole, rest = divmod(b, 1)
    return f"{whole}+{rest}" if whole else str(rest)


def _sig(chart, measure):
    sig = [4, 4]
    for idx, s in chart["beat"].get("time_sig", [[0, [4, 4]]]):
        if idx <= measure:
            sig = s
    return sig


def _button_events(chart):
    """(kind, lane, y, length) for every BT/FX note."""
    note = chart.get("note", {})
    for kind in ("bt", "fx"):
        for lane, notes in enumerate(note.get(kind, [])):
            for y, length in _notes(notes):
                yield kind, lane, y, length


def _laser_spans(chart):
    """(side, start, end, slam pulses) per laser section."""
    for side, sections in enumerate(chart.get("note", {}).get("laser", [])):
        for y, points, *_ in sections:
            slams = [y + ry for ry, v, *_ in points if _value(v)[0] != _value(v)[1]]
            yield side, y, y + points[-1][0], slams


def _moving_laser_ranges(chart):
    """(start, end) pulse ranges where a knob must be turned: slopes, and slams +-1/8 beat.

    A stationary laser can be left alone, so it does not occupy a hand.
    """
    pad = 30
    for sections in chart.get("note", {}).get("laser", []):
        for y, points, *_ in sections:
            pts = [(y + ry, *_value(v)) for ry, v, *_ in points]
            for ya, va, vfa in pts:
                if va != vfa:
                    yield ya - pad, ya + pad + 1
            for (ya, _, vfa), (yb, vb, _) in zip(pts, pts[1:]):
                if vfa != vb:
                    yield ya, yb


def _hands_for_buttons(pressed) -> int:
    """Minimum hands to press the buttons, each hand spanning two adjacent lanes."""
    if not pressed:
        return 0
    # FX buttons sit between the BT lanes toward the centre: FX-L reaches like B,
    # FX-R like C, so FX-L+FX-R or A+FX-L fit one hand while A+FX-R does not.
    lanes = sorted({l if k == "bt" else l + 1 for k, l in pressed})
    hands, reach = 0, -1
    for lane in lanes:
        if lane > reach:
            hands += 1
            reach = lane + 1
    return hands


def lint(chart: dict, analysis: dict | None = None) -> list[Finding]:
    timing = TimingMap(chart["beat"])
    out: list[Finding] = []
    events = sorted(_button_events(chart), key=lambda e: e[2])
    lasers = list(_laser_spans(chart))

    # Jacks: same lane, chip/long starts too close in time.
    last: dict[tuple[str, int], int] = {}
    for kind, lane, y, length in events:
        key = (kind, lane)
        if key in last:
            prev_y = last[key]
            dt = timing.pulse_to_sec(y) - timing.pulse_to_sec(prev_y)
            if dt < JACK_MIN_SEC:
                name = LANES[lane] if kind == "bt" else "FX-" + FX_LANES[lane]
                out.append(Finding("warning", "fast-jack", _where(timing, chart, y),
                                   f"{name} repeats after {dt * 1000:.0f} ms"))
        last[key] = y + length

    # Very short long notes read as chips but must be held.
    for kind, lane, y, length in events:
        if length:
            den = _sig(chart, timing.pulse_to_measure(y)[0])[1]
            if Fraction(length, 960 // den) < SHORT_LONG_BEATS:
                out.append(Finding("warning", "short-long", _where(timing, chart, y),
                                   f"long note of {length} pulses; use a chip or lengthen it"))

    # Hand load: each active knob takes a hand; one hand covers two adjacent BT
    # lanes plus the FX button under them (FX-L under A/B, FX-R under C/D).
    starts = sorted({y for _, _, y, _ in events})
    moving = [list(_moving_laser_ranges({"note": {"laser": [side]}}))
              for side in chart.get("note", {}).get("laser", [])]
    for y in starts:
        knobs = sum(1 for ranges in moving if any(a <= y < b for a, b in ranges))
        pressed = [(kind, lane) for kind, lane, ny, length in events
                   if ny == y or (length and ny < y < ny + length)]
        hands = knobs + _hands_for_buttons(pressed)
        if hands > 2:
            names = " ".join(LANES[l] if k == "bt" else "FX-" + FX_LANES[l] for k, l in pressed)
            out.append(Finding("warning", "hand-overload", _where(timing, chart, y),
                               f"{knobs} knob(s) + buttons {names} need {hands} hands"))

    if analysis is not None:
        out.extend(_lint_against_audio(chart, timing, events, analysis))
    return out


def _lint_against_audio(chart, timing, events, analysis):
    out = []
    duration = analysis["audio"]["duration_sec"]
    offset = chart.get("audio", {}).get("bgm", {}).get("offset", 0) / 1000
    onset_pulses = set()
    for m in analysis["measures"]:
        den = analysis["tempo"]["time_sig"][1]
        base = timing.measure_to_pulse(m["index"])
        # A kick may only show up in the low band, a hat only in the high band.
        for b, _ in (o for band in m["onsets"].values() for o in band):
            onset_pulses.add(int(round(base + b * 960 / den)))
    unaligned = []
    for kind, lane, y, length in events:
        t = timing.pulse_to_sec(y + length) + offset
        if t > duration:
            out.append(Finding("warning", "after-audio", _where(timing, chart, y), "note ends after the audio"))
        if not any(abs(y - p) <= 10 for p in onset_pulses):
            unaligned.append(y)
    if events:
        ratio = len(unaligned) / len(events)
        if ratio > 0.15:
            sample = ", ".join(_where(timing, chart, y) for y in sorted(set(unaligned))[:12])
            out.append(Finding("info", "unaligned", "-",
                               f"{ratio:.0%} of button notes have no detected onset nearby (e.g. {sample})"))
    button_counts = {}
    for _, _, y, _ in events:
        idx = timing.pulse_to_measure(y)[0]
        button_counts[idx] = button_counts.get(idx, 0) + 1
    covered = {timing.pulse_to_measure(y)[0] for _, _, y, _ in events}
    for side, a, b, _ in _laser_spans(chart):
        covered.update(range(timing.pulse_to_measure(a)[0], timing.pulse_to_measure(b)[0] + 1))
    for m in analysis["measures"]:
        if m["energy"] >= 0.6 and m["index"] not in covered:
            out.append(Finding("info", "empty-loud", f"m{m['index']}", "loud measure with no notes"))
        if "stems" in m:
            vocal = sum(1 for _, strength in m["stems"]["onsets"].get("vocal", []) if strength >= 0.3)
            buttons = button_counts.get(m["index"], 0)
            if vocal >= 4 and buttons < 4:
                out.append(Finding("info", "thin", f"m{m['index']}",
                                   f"vocal sings {vocal} notes, {buttons} button notes: follow its rhythm or make the rest deliberate"))
    return out


def stats(chart: dict) -> dict:
    timing = TimingMap(chart["beat"])
    events = list(_button_events(chart))
    lasers = list(_laser_spans(chart))
    times = sorted(timing.pulse_to_sec(y) for _, _, y, _ in events)
    times += [timing.pulse_to_sec(s) for *_, slams in lasers for s in slams]
    times.sort()
    first = times[0] if times else 0.0
    last = times[-1] if times else 0.0
    span = max(last - first, 1e-9)
    peak, j = 0, 0
    for i, t in enumerate(times):
        while times[j] < t - MAX_PEAK_WINDOW_SEC:
            j += 1
        peak = max(peak, i - j + 1)
    chips = sum(1 for e in events if e[3] == 0)
    slams = sum(len(s) for *_, s in lasers)
    s = {
        "bt_chips": sum(1 for e in events if e[0] == "bt" and e[3] == 0),
        "bt_longs": sum(1 for e in events if e[0] == "bt" and e[3] > 0),
        "fx_chips": sum(1 for e in events if e[0] == "fx" and e[3] == 0),
        "fx_longs": sum(1 for e in events if e[0] == "fx" and e[3] > 0),
        "laser_sections": len(lasers),
        "slams": slams,
        "duration_sec": round(span, 2),
        "avg_nps": round((chips + slams) / span, 2),
        "peak_nps": round(peak / MAX_PEAK_WINDOW_SEC, 2),
        "laser_ratio": round(sum(timing.pulse_to_sec(b) - timing.pulse_to_sec(a) for _, a, b, _ in lasers) / span, 2),
        "chains": len(chain_ticks(chart)),
    }
    s.update(_complexity(chart, timing, events, span))
    s["level_estimate"] = estimate_level(s)
    return s


def chain_ticks(chart: dict) -> list[int]:
    """Pulses of every chain (combo) event, counted as K-Shoot MANIA v2 does
    (Judgment/ButtonLaneJudgment.cpp, LaserLaneJudgment.cpp)."""
    ticks = []
    for _, _, y, length in _button_events(chart):
        step = 120 if _bpm_at(chart, y) >= HALVE_CHAIN_BPM else 60
        if length == 0:
            ticks.append(y)
        elif length < step * 2:
            ticks.append(y)
        elif length <= step * 3:
            ticks.append(y + step)
        else:
            # skip the first grid tick after the start; the last one stands for the end
            ticks += range(((y + step - 1) // step + 1) * step, y + length - step, step)
    for sections in chart.get("note", {}).get("laser", []):
        for y, points, *_ in sections:
            pts = [(y + ry, *_value(v)) for ry, v, *_ in points]
            ticks += [ya for ya, va, vfa in pts if va != vfa]
            for (ya, va, vfa), (yb, vb, _) in zip(pts, pts[1:]):
                start = ya
                if va != vfa:
                    if vb == vfa and yb - ya <= 30:   # the slam's own landing point
                        continue
                    start += 30                        # no line ticks within a 32nd after a slam
                step = 120 if _bpm_at(chart, start) >= HALVE_CHAIN_BPM else 60
                ticks += range((start + step - 1) // step * step, yb, step)
    return sorted(ticks)


def _complexity(chart, timing, events, span):
    """Features that separate the high levels: chords, 16th streams, knob + button overlap."""
    starts: dict[int, int] = {}
    for _, _, y, _ in events:
        starts[y] = starts.get(y, 0) + 1
    ys = sorted(starts)
    chords = sum(1 for y in ys if starts[y] >= 2)
    # Longest run of starts no more than a 16th note apart (by time, so BPM matters).
    best = run_start = 0.0
    secs = [timing.pulse_to_sec(y) for y in ys]
    for i in range(1, len(secs)):
        beat = 60.0 / _bpm_at(chart, ys[i])
        if secs[i] - secs[i - 1] > beat / 4 + 1e-6:
            run_start = secs[i]
        best = max(best, secs[i] - run_start)
    moving = [r for side in chart.get("note", {}).get("laser", [])
              for r in _moving_laser_ranges({"note": {"laser": [side]}})]
    move_sec = sum(timing.pulse_to_sec(b) - timing.pulse_to_sec(a) for a, b in moving)
    with_knob = sum(1 for _, _, y, _ in events if any(a <= y < b for a, b in moving))
    n = max(len(events), 1)
    return {
        "chord_ratio": round(chords / max(len(ys), 1), 3),
        "stream16_max_sec": round(best, 2),
        "knob_move_ratio": round(move_sec / span, 3),
        "knob_button_ratio": round(with_knob / n, 3),
        "long_ratio": round(sum(1 for e in events if e[3] > 0) / n, 3),
        "max_bpm": max(v for _, v in chart["beat"]["bpm"]),
    }


def _bpm_at(chart, y):
    bpm = chart["beat"]["bpm"][0][1]
    for py, v in chart["beat"]["bpm"]:
        if py <= y:
            bpm = v
    return bpm


# Weighted least-squares fit (tests/eval/fit_level.py) on the 36 official charts
# (levels 1-16) and ~1600 local sdvx.in charts (17-20): MAE ~0.7 levels on both.
LEVEL_COEF = {"log_avg_nps": 4.066, "log_peak_nps": 2.302, "laser_ratio": 2.463,
              "stream16_max_sec": 0.102, "knob_button_ratio": 5.026, "bias": 0.106}
FEATURES = tuple(k for k in LEVEL_COEF if k != "bias")


def level_features(s: dict) -> dict:
    """Stats as seen by the level model (density enters on a log scale)."""
    return {**s, "log_avg_nps": math.log(max(s["avg_nps"], 0.1)),
            "log_peak_nps": math.log(max(s["peak_nps"], 0.5))}


def estimate_level(s: dict) -> float:
    f = level_features(s)
    v = LEVEL_COEF["bias"] + sum(LEVEL_COEF[k] * f[k] for k in FEATURES)
    return round(min(20.0, max(1.0, v)), 1)
