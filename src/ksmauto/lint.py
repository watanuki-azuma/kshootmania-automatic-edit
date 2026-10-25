"""Playability lint and density statistics for KSON charts."""

from __future__ import annotations

import math
import json

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from importlib.resources import files

from .timing import TimingMap

LANES = ["A", "B", "C", "D"]
FX_LANES = ["L", "R"]

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
    """Minimum span-3 hands; an FX needs both of its underlying BT lanes."""
    mask = sum(1 << l for l in {l if k == 'bt' else l + 4 for k, l in pressed})
    return button_hands(mask)


# A-C + FX-L and B-D + FX-R. A hand can travel to either window.
HAND_REACH = (0b010111, 0b101110)


@lru_cache(maxsize=64)
def button_hands(mask):
    if not mask:
        return 0
    # Exact set cover, with no assumption that the answer fits two hands.
    return 1 + min(button_hands(mask & ~reach) for reach in HAND_REACH if mask & reach)


@lru_cache(maxsize=1)
def hand_policy():
    """Corpus aggregates shipped with the package (no chart fragments)."""
    return json.loads(files('ksmauto').joinpath('data/hand_categories.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def placement_verdicts():
    return json.loads(files('ksmauto').joinpath('data/placement_verdicts.json').read_text(encoding='utf-8'))


def level_group(level):
    level = float(level or 0)
    if level < 17:
        return 'ksm'
    return '17' if level <= 17.4 else ('18' if level < 19 else '19-20')


def merged(ranges):
    out = []
    for a, b in sorted(ranges, key=lambda r: (r[0], r[1])):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def contains(ranges, y):
    i = bisect_right(ranges, [y, math.inf]) - 1
    return i >= 0 and y < ranges[i][1]


def overlaps(ranges, a, b):
    if b <= a:
        return contains(ranges, a)
    i = bisect_right(ranges, [a, math.inf]) - 1
    return (i >= 0 and ranges[i][1] > a) or (i + 1 < len(ranges) and ranges[i + 1][0] < b)


def covers(ranges, a, b):
    if b <= a:
        return contains(ranges, a)
    i = bisect_right(ranges, [a, math.inf]) - 1
    return i >= 0 and ranges[i][1] >= b


def home(lane):
    return int(lane in (2, 3, 5))


def laser_demands(chart, timing):
    """Indexed slope/section/slam geometry. Width is in normal lane widths.

    Contiguous slopes form a movement, ending at a stationary segment or the
    section end. BPM boundaries split speed evaluation, not movement endpoints.
    Curves retain their control point for instantaneous speed evaluation.
    """
    out = []
    lasers = chart.get('note', {}).get('laser', [])
    for side in (0, 1):
        slopes, slams = [], []
        for y, points, *width in (lasers[side] if side < len(lasers) else []):
            w = width[0] if width else 1
            pts = [(y + p[0], *_value(p[1]), p[2] if len(p) > 2 else [0, 0]) for p in points]
            if not pts:
                continue
            slams.extend((a - 30, a + 31) for a, v, vf, _ in pts if v != vf)
            movement_end = pts[-1][0]
            rows = []
            for (a, _, va, curve), (b, vb, _, _) in reversed(list(zip(pts, pts[1:]))):
                if va == vb:
                    movement_end = a
                elif b > a:
                    rows.append((a, b, abs(vb - va) * w, curve, movement_end))
            slopes.extend(reversed(rows))
        slopes.sort()
        out.append({'slopes': slopes, 'starts': [r[0] for r in slopes],
                    'slams': merged(slams)})
    return out


def slope_at(profile, timing, y):
    i = bisect_right(profile['starts'], y) - 1
    if i < 0:
        return None
    a, b, distance, curve, end = profile['slopes'][i]
    if not a <= y < b:
        return None
    x = (y - a) / (b - a)
    ca, cb = curve
    derivative = 1.0
    if ca != cb:
        root = math.sqrt(max(0, ca * ca + x - 2 * ca * x))
        t = (ca - root) / (2 * ca - 1) if ca < 0.25 else x / (ca + root)
        dx = 2 * ((1 - t) * ca + t * (1 - ca))
        dy = 2 * ((1 - t) * cb + t * (1 - cb))
        derivative = dy / dx if dx else math.inf
    # A pulse-local speed respects tempo changes inside a slope.
    seconds_per_pulse = 60 / (240 * timing._bpms[max(0, bisect_right(timing._pulses, y) - 1)])
    speed = distance * derivative / ((b - a) * seconds_per_pulse)
    return speed, max(0, timing.pulse_to_sec(end) - timing.pulse_to_sec(y))


def demand_at(profile, timing, y, thresholds):
    if contains(profile['slams'], y):
        return 'slam'
    slope = slope_at(profile, timing, y)
    if slope:
        speed, remaining = slope
        if remaining <= thresholds['ending_sec'] + 1e-9:
            return 'ending'
        return 'steep' if speed > thresholds['steep_widths_per_sec'] else 'gentle'
    # Absent lasers and stationary lasers both leave the hand free.
    return 'still'


DEMAND_ORDER = {'still': 0, 'ending': 1, 'gentle': 2, 'steep': 3, 'slam': 4}
BUTTON_NAMES = ('A', 'B', 'C', 'D', 'FX-L', 'FX-R')
MIRROR_LANES = (3, 2, 1, 0, 5, 4)


def category_key(demands, pressed):
    """Knob demands, minimum button hands, and unavoidable far-side reach.

    Prefer the less busy knob's hand for a one-hand press. Crossing is required
    when that hand must leave its home span-3 window. Two button hands already
    imply borrowing every busy knob hand; starts and holds have equal weight.
    """
    ds = list(demands)
    lanes = set(pressed)
    if DEMAND_ORDER[ds[1]] > DEMAND_ORDER[ds[0]]:
        ds.reverse()
        lanes = {MIRROR_LANES[l] for l in lanes}
    mask = sum(1 << l for l in lanes)
    hands = button_hands(mask)
    crossing = hands == 1 and ds[0] != ds[1] and bool(mask & ~HAND_REACH[1])
    return f'{",".join(ds)}|{hands}|{"crossing" if crossing else "home"}'


def effective_hands(key):
    demands, hands, _ = key.split('|')
    weight = {'still': 0, 'ending': .5, 'gentle': .5, 'steep': 1, 'slam': 1}
    return int(hands) + sum(weight[d] for d in demands.split(','))


def button_categories(chart, timing, thresholds, profiles=None):
    profiles = profiles if profiles is not None else laser_demands(chart, timing)
    starts = defaultdict(list)
    for kind, lane, y, length in _button_events(chart):
        starts[y].append((lane if kind == 'bt' else lane + 4, length))
    active = []
    for y, notes in sorted(starts.items()):
        active = [(b, l) for b, l in active if b > y]
        pressed = [(l, 'S') for l, _ in notes] + [(l, 'H') for _, l in active]
        demands = [demand_at(p, timing, y, thresholds) for p in profiles]
        yield y, category_key(demands, [l for l, _ in pressed]), demands, pressed
        active.extend((y + length, l) for l, length in notes if length)


def jack_context(chart, timing, thresholds, profiles=None):
    """Shared interval classifier for mining and lint, including assist."""
    profiles = profiles if profiles is not None else laser_demands(chart, timing)
    moving = [merged(_moving_laser_ranges({'note': {'laser': [lane]}}))
              for lane in chart.get('note', {}).get('laser', [])]
    moving += [[] for _ in range(2 - len(moving))]
    starts, holds = [[], []], [[], []]
    for kind, lane, y, length in _button_events(chart):
        side = home(lane if kind == 'bt' else lane + 4)
        starts[side].append(y)
        if length:
            holds[side].append((y, y + length))
    busy = [merged([*moving[s], *holds[s]]) for s in (0, 1)]
    hard = []
    for side, p in enumerate(profiles):
        ranges = list(p['slams']) + holds[side]
        # Split at tempo boundaries and the assist window. A quadratic graph's
        # derivative is monotone, so each piece has at most one speed crossing.
        for a, b, _, curve, end in p['slopes']:
            stop = min(b, timing.sec_to_pulse(timing.pulse_to_sec(end) - thresholds['ending_sec']))
            cuts = [a, *[v for v in timing._pulses if a < v < stop], stop]
            for x, z in zip(cuts, cuts[1:]):
                if x >= z:
                    continue
                limit = thresholds['steep_widths_per_sec']
                left = slope_at(p, timing, x)[0] > limit
                right = slope_at(p, timing, math.nextafter(z, x))[0] > limit
                if left == right:
                    if left:
                        ranges.append((x, z))
                else:
                    lo, hi = x, z
                    for _ in range(48):
                        mid = (lo + hi) / 2
                        if (slope_at(p, timing, mid)[0] > limit) == left:
                            lo = mid
                        else:
                            hi = mid
                    cross = (lo + hi) / 2
                    ranges.append((x, cross) if left else (cross, z))
        hard.append(merged(ranges))
    return {'moving': moving, 'busy': busy, 'hard': hard,
            'starts': [sorted(set(s)) for s in starts]}


def jack_interval_class(context, side, a, b):
    other = 1 - side
    if overlaps(context['busy'][other], a, b) and not overlaps(context['hard'][other], a, b):
        return 'assisted'
    if covers(context['busy'][other], a, b):
        return 'one-hand'
    ss = context['starts'][other]
    i = bisect_right(ss, a)
    if not overlaps(context['busy'][other], a, b) and not (i < len(ss) and ss[i] < b):
        return 'two-hand'
    return 'mixed'


def jack_intervals(chart, timing, thresholds, profiles=None):
    context = jack_context(chart, timing, thresholds, profiles)
    lanes = [[] for _ in BUTTON_NAMES]
    for kind, lane, y, length in _button_events(chart):
        lanes[lane if kind == 'bt' else lane + 4].append((y, length))
    for lane, notes in enumerate(lanes):
        notes.sort()
        for (a, length), (b, next_length) in zip(notes, notes[1:]):
            if next_length or b < a + length:
                continue
            a += length
            side = home(lane)
            if covers(context['moving'][side], a, b) and not overlaps(context['moving'][1 - side], a, b):
                side = 1 - side
            cls = jack_interval_class(context, side, a, b)
            yield lane, a, b, length, cls


JACK_BANDS_MS = (0, 60, 70, 80, 90, 100, 120)


def jack_band(dt):
    # Integrating BPMs can place exact millisecond boundaries just below a bin.
    return max(0, bisect_right(JACK_BANDS_MS, dt + 1e-6) - 1)


def _ms(value):
    return 'off' if value is None else f'{value:g} ms'


def jack_key(group, cls, kind):
    return f'jack:{group}:{cls}:{kind}'


def _apply_verdict(out, verdicts, key, level, where):
    if key not in verdicts:
        return False
    verdict = verdicts[key]
    if verdict == 'forbid':
        out.append(Finding('warning', 'placement-forbidden', where, f'{key}: forbidden by human verdict'))
    elif isinstance(verdict, dict) and level < verdict['min_level']:
        out.append(Finding('warning', 'placement-min-level', where,
                           f'{key}: requires Lv{verdict["min_level"]}, chart is Lv{level:g}'))
    return True


def lint(chart: dict, analysis: dict | None = None) -> list[Finding]:
    timing = TimingMap(chart["beat"])
    out: list[Finding] = []
    events = sorted(_button_events(chart), key=lambda e: e[2])
    policy = hand_policy()
    verdicts = placement_verdicts()
    thresholds = policy['thresholds']
    level = float(chart.get('meta', {}).get('level', 0) or 0)
    group = level_group(level)
    profiles = laser_demands(chart, timing)

    for lane, a, b, _, cls in jack_intervals(chart, timing, thresholds, profiles):
        cls = 'one-hand' if cls == 'mixed' else cls
        kind = 'BT' if lane < 4 else 'FX'
        row = policy['jacks'][group][cls][kind]
        limit, minimum = row['p1_ms'], row['robust_min_ms']
        verdict = verdicts.get(jack_key(group, cls, kind))
        if isinstance(verdict, dict) and 'info_ms' in verdict:
            # Human thresholds replace the corpus ones; null turns that level off.
            limit, minimum = verdict['info_ms'], verdict['warn_ms']
        elif _apply_verdict(out, verdicts, jack_key(group, cls, kind), level, _where(timing, chart, b)):
            continue
        dt = (timing.pulse_to_sec(b) - timing.pulse_to_sec(a)) * 1000
        warning = minimum is not None and dt < minimum - 1e-6
        if warning or (limit is not None and dt < limit - 1e-6):
            rule = 'fast-jack' if cls == 'two-hand' else 'fast-jack-one-hand'
            out.append(Finding('warning' if warning else 'info', rule, _where(timing, chart, b),
                               f'{jack_key(group, cls, kind)}: {BUTTON_NAMES[lane]} repeats after {dt:.1f} ms ({cls}); '
                               f'info below {_ms(limit)}, warning below {_ms(minimum)}'))

    # Very short long notes read as chips but must be held.
    for kind, lane, y, length in events:
        if length:
            den = _sig(chart, timing.pulse_to_measure(y)[0])[1]
            if Fraction(length, 960 // den) < SHORT_LONG_BEATS:
                out.append(Finding("warning", "short-long", _where(timing, chart, y),
                                   f"long note of {length} pulses; use a chip or lengthen it"))

    for y, key, _, _ in button_categories(chart, timing, thresholds, profiles):
        if _apply_verdict(out, verdicts, key, level, _where(timing, chart, y)):
            continue
        if effective_hands(key) <= 2:
            continue
        row = policy['categories'].get(key)
        if row is None or not any(v['count'] for v in row.values()):
            out.append(Finding('warning', 'hand-impossible', _where(timing, chart, y),
                               f'{key}: never observed in the official corpus'))
            continue
        evidence = row[group]
        rate = evidence['per_100_measures']
        if rate < policy['rare_per_100_measures']:
            out.append(Finding('info', 'hand-rare', _where(timing, chart, y),
                               f'{key}: official Lv{group}: {rate:.2f}/100 measures, '
                               f'{evidence["charts"]} charts'))

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
