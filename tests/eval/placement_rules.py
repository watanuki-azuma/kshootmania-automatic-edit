"""Mine placement evidence; never change lint policy or redistribute chart data.

Usage: uv run python tests/eval/placement_rules.py [--workers 4]
Only aggregate statistics and at most five locations per group/rule are reported.
Per-chart results and source/decode diagnostics stay in ignored out/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ksmauto.ksh import load_ksh
from ksmauto.lint import _button_events, _hands_for_buttons, _moving_laser_ranges, _value, stats
from ksmauto.timing import TimingMap

try:
    from .sdvxin_stats import usable
except ImportError:
    from sdvxin_stats import usable

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'out' / 'placement_rules_cache.jsonl'
GROUPS = ('17', '18', '19-20', 'ksm')
NAMES = ('A', 'B', 'C', 'D', 'FL', 'FR')
RULES = {
    'hand-overload': '既存 lint と同じ、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数）',
    'jack-two-hand': '同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし）',
    'jack-one-hand': '同じ反復で反対手が全区間、つまみまたは自側 long に占有されるもの',
    'trill-one-hand': '反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数）',
    'stream-density': 'ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数）',
    'chord-shapes': 'ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数）',
    'knob-crossing-press': '片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数）',
    'both-knobs-and-button': '両つまみが動く時刻のボタン開始（時刻数、レーン別内訳）',
    'slam-with-button': '直角と同 pulse のボタン開始集合（直角数、右直角を左右反転）',
    'slam-interval': '同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える',
    'laser-zigzag': '同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ',
    'laser-crossing': '両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始）',
    'laser-gap': '同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む）',
    'hold-and-chip': '保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数）',
    'long-end-to-chip': '同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし）',
    'short-long': '長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計）',
    'offgrid': '全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数）',
    'fx-long-with-bt-chips': 'FL 保持中の A/B chip、および FR 保持中の C/D chip（対数）',
    'button-during-slam-same-hand': '直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数）',
    'wide-laser': '幅指定が 2 のレーザー区間（区間数）',
}
# All positions in the report are zero-based TimingMap measure indices.


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
    i = bisect_right(ranges, [a, math.inf]) - 1
    return (i >= 0 and ranges[i][1] > a) or (i + 1 < len(ranges) and ranges[i + 1][0] < b)


def covers(ranges, a, b):
    if b <= a:
        return contains(ranges, a)
    i = bisect_right(ranges, [a, math.inf]) - 1
    return i >= 0 and ranges[i][1] >= b


def home(lane):
    return int(lane in (2, 3, 5))


def pressed_lanes(lanes):
    return [('bt', l) if l < 4 else ('fx', l - 4) for l in lanes]


def shape(lanes, mirror=False):
    flip = (3, 2, 1, 0, 5, 4)
    return '+'.join(NAMES[l] for l in sorted(flip[l] if mirror else l for l in lanes))


def quantiles(values, duration=False, chart=False):
    if not values:
        return {'n': 0}
    values = sorted(values)

    def q(p):
        x = (len(values) - 1) * p / 100
        a, b = math.floor(x), math.ceil(x)
        return round(values[a] + (values[b] - values[a]) * (x - a), 6)

    ps = (50, 99) if chart else ((50, 99, 99.9) if duration else (0.1, 1, 5, 50))
    return {'n': len(values), 'min': values[0], **{f'p{p}': q(p) for p in ps}, 'max': values[-1]}


def curve_at(curve, x):
    """Quadratic Bezier graph value, as in the viewer / libkson."""
    a, b = curve
    if a == b:
        return x
    root = math.sqrt(max(0, a * a + x - 2 * a * x))
    t = (a - root) / (2 * a - 1) if a < 0.25 else x / (a + root)
    return min(1, max(0, 2 * (1 - t) * t * b + t * t))


def flatten_curve(a, b, va, vb, curve):
    """Polyline with displayed vertical error <= 1e-9 normal lane widths.

    De Casteljau subdivision bounds the error using the control point's
    deviation from the chord. Straight segments retain exact endpoints.
    """
    def split(p, q, r):
        x, v = p
        z, w = r
        error = abs(q[1] - v - (w - v) * (q[0] - x) / (z - x))
        if error <= 1e-9 or z - x <= 1e-9:
            yield x, z, v, w
            return
        pq = tuple((u + v) / 2 for u, v in zip(p, q))
        qr = tuple((u + v) / 2 for u, v in zip(q, r))
        mid = tuple((u + v) / 2 for u, v in zip(pq, qr))
        yield from split(p, pq, mid)
        yield from split(mid, qr, r)

    if curve[0] == curve[1] or va == vb:
        yield a, b, va, vb
    else:
        control = (a + (b - a) * curve[0], va + (vb - va) * curve[1])
        yield from split((a, va), control, (b, vb))


def laser_geometry(lasers):
    """Displayed-position segments and sections, including curves/wide scaling."""
    segments, sections, slams = [[], []], [[], []], [[], []]
    for side, lane in enumerate(lasers):
        for sec in lane:
            start, points, *width = sec
            w = width[0] if width else 1
            pts = [(start + p[0], *_value(p[1]), p[2] if len(p) > 2 else [0, 0]) for p in points]
            scale = lambda v: 0.5 + (v - 0.5) * w
            sections[side].append((start, pts[-1][0], pts, w))
            for y, v, vf, _ in pts:
                if v != vf:
                    slams[side].append((y, 1 if vf > v else -1, start))
            for (a, _, va, curve), (b, vb, _, _) in zip(pts, pts[1:]):
                if b > a:
                    segments[side].extend(flatten_curve(a, b, scale(va), scale(vb), curve))
    return segments, sections, slams


def crossing_ranges(segments):
    """Solve L(y) > R(y) exactly on overlapping linear segments."""
    left, right = segments
    i = j = 0
    found = []
    while i < len(left) and j < len(right):
        la, lb, lv, lw = left[i]
        ra, rb, rv, rw = right[j]
        a, b = max(la, ra), min(lb, rb)
        if a < b:
            def diff(y):
                return lv + (lw - lv) * (y - la) / (lb - la) - rv - (rw - rv) * (y - ra) / (rb - ra)
            da, db = diff(a), diff(b)
            if da > 0 and db > 0:
                found.append((a, b))
            elif da > 0 or db > 0:
                zero = a + (b - a) * da / (da - db)
                found.append((a, zero) if da > 0 else (zero, b))
        if lb <= rb:
            i += 1
        if rb <= lb:
            j += 1
    return merged(found)


def tally(chart):
    """Return per-chart counts, metric samples and bounded example locations.

    Busy spans are half-open; long endpoints are free. Interval classification
    uses (a,b) for intervening starts, and [a,b) for continuous occupancy.
    Partially occupied intervals are retained as jack-mixed, never silently
    assigned to one-hand or two-hand. Instantaneous intervening home starts
    prevent a completely free interval but cannot cover the whole interval.
    """
    timing = TimingMap(chart['beat'])
    events = sorted((y, lane if kind == 'bt' else lane + 4, length)
                    for kind, lane, y, length in _button_events(chart))
    lasers = chart.get('note', {}).get('laser', [[], []])
    lasers = [*lasers, *([[]] * (2 - len(lasers)))]
    moving = [merged(_moving_laser_ranges({'note': {'laser': [side]}})) for side in lasers]
    segments, sections, slams = laser_geometry(lasers)
    unpadded = [merged((a, b) for _, _, pts, _ in lane
                       for (a, _, va, _), (b, vb, _, _) in zip(pts, pts[1:]) if va != vb)
                for lane in sections]
    slam_ys = [{y for y, _, _ in lane} for lane in slams]
    result = {rule: {'count': 0, 'by': {}, 'metrics': {}, 'examples': []} for rule in RULES}
    # The mixed bucket documents intervals that satisfy neither requested rule.
    result['jack-mixed'] = {'count': 0, 'by': {}, 'metrics': {}, 'examples': []}
    counters = defaultdict(Counter)
    metrics = defaultdict(lambda: defaultdict(list))
    examples = defaultdict(list)

    def add(rule, y, detail='', metric=None, value=None, rank=0):
        result[rule]['count'] += 1
        if detail:
            counters[rule][detail] += 1
        if metric is not None:
            metrics[rule][metric].append(value)
        m = timing.pulse_to_measure(y)[0]
        ex = {'measure': m, 'detail': detail, 'rank': rank}
        if metric:
            ex.update(metric=metric, value=value)
        if not any(e['measure'] == m and e['detail'] == detail for e in examples[rule]):
            examples[rule].append(ex)
            examples[rule].sort(key=lambda e: (e['rank'], e['measure'], e['detail']))
            del examples[rule][5:]

    def sample(rule, metric, value):
        metrics[rule][metric].append(value)

    def ms(a, b):
        return round((timing.pulse_to_sec(b) - timing.pulse_to_sec(a)) * 1000, 6)

    starts = defaultdict(list)
    lane_events = [[] for _ in NAMES]
    longs = []
    home_starts = [[], []]
    for y, lane, length in events:
        starts[y].append((lane, length))
        lane_events[lane].append((y, length))
        home_starts[home(lane)].append(y)
        if length:
            longs.append((y, y + length, lane))
    ys = sorted(starts)
    home_starts = [sorted(set(s)) for s in home_starts]
    busy = [merged([*moving[side], *((a, b) for a, b, l in longs if home(l) == side)])
            for side in (0, 1)]

    def intervening(side, a, b):
        ss = home_starts[side]
        i = bisect_right(ss, a)
        return i < len(ss) and ss[i] < b

    def interval_class(side, a, b):
        other = 1 - side
        if covers(busy[other], a, b):
            return 'one-hand'
        if not overlaps(busy[other], a, b) and not intervening(other, a, b):
            return 'two-hand'
        return 'mixed'

    def busy_at(side, y):
        return contains(busy[side], y)

    # Consecutive same-lane events; the second must be a chip.
    for lane, notes in enumerate(lane_events):
        for (a, length), (b, next_length) in zip(notes, notes[1:]):
            if next_length or b < a + length:
                continue
            a += length
            side = home(lane)
            if covers(moving[side], a, b) and not overlaps(moving[1 - side], a, b):
                side = 1 - side
            cls = interval_class(side, a, b)
            dt = ms(a, b)
            kind = 'BT' if lane < 4 else 'FX'
            detail = kind + (':long-end' if length else ':chip')
            add('jack-' + cls, b, detail, kind + '_interval_ms', dt, dt)
            counters['jack-' + cls]['under_75ms'] += dt < 75
            if cls == 'mixed':
                reason = 'partial-occupancy' if overlaps(busy[1 - side], a, b) else 'intervening-start-only'
                counters['jack-mixed']['reason:' + reason] += 1
            if length:
                add('long-end-to-chip', b, NAMES[lane], 'interval_ms', dt, dt)
                counters['long-end-to-chip']['under_75ms'] += dt < 75

    # Maximal alternating single-chip sequences. Other starts in the performing
    # hand's home lanes break a run; other-hand starts may coexist.
    seen_runs = set()
    for pair in ((0, 1), (2, 3), (1, 2)):
        hands = (0, 1) if pair == (1, 2) else (home(pair[0]),)
        for side in hands:
            relevant = sorted(set(y for y, lane, _ in events if home(lane) == side or lane in pair))
            run = []

            def flush():
                key = tuple(run)
                if len(run) >= 3 and key not in seen_runs:
                    seen_runs.add(key)
                    add('trill-one-hand', run[0][0], shape(pair), 'run_hits', len(run), -len(run))
                    for (a, _), (b, _) in zip(run, run[1:]):
                        sample('trill-one-hand', 'hit_interval_ms', ms(a, b))
                run.clear()

            for y in relevant:
                notes = [(l, length) for l, length in starts[y] if home(l) == side or l in pair]
                if len(notes) != 1 or notes[0][0] not in pair or notes[0][1] or contains(moving[side], y):
                    flush()
                    continue
                lane = notes[0][0]
                if run and (lane == run[-1][1] or interval_class(side, run[-1][0], y) != 'one-hand'
                            or overlaps(moving[side], run[-1][0], y)):
                    flush()
                run.append((y, lane))
            flush()
    sample('trill-one-hand', 'chart_longest_run_hits', max(metrics['trill-one-hand']['run_hits'], default=0))

    secs = [timing.pulse_to_sec(y) for y in ys]
    if ys:
        for window in (1, 4):
            j, best, best_y = 0, 0, ys[0]
            for i, sec in enumerate(secs):
                # Half-open window (t-window,t]; exact 1s spacing is not double counted.
                while secs[j] <= sec - window:
                    j += 1
                if i - j + 1 > best:
                    best, best_y = i - j + 1, ys[i]
            sample('stream-density', f'peak_{window}s_nps', best / window)
        stream = stats(chart)['stream16_max_sec']
        add('stream-density', best_y, 'chart', 'stream16_max_sec', stream, -stream)

    # Sweep held notes to match lint's strict ny < y < ny+length test exactly.
    active = []
    for y in ys:
        active = [(a, b, l) for a, b, l in active if b > y]
        lanes = [l for l, _ in starts[y]]
        turning = [contains(s, y) for s in moving]
        pressed = pressed_lanes(lanes + [l for _, _, l in active])
        if sum(turning) + _hands_for_buttons(pressed) > 2:
            add('hand-overload', y, f'{sum(turning)} knobs:' + shape(set(lanes + [l for _, _, l in active])))
            knobs = sum(contains(unpadded[s], y) or y in slam_ys[s] for s in (0, 1))
            why = 'without-slam-padding' if knobs + _hands_for_buttons(pressed) > 2 else 'slam-padding-only'
            counters['hand-overload']['cause:' + why] += 1
        if not any(turning) or sum(turning) == 1:
            mirror = turning[1]
            mode = 'knob:' if any(turning) else 'free:'
            add('chord-shapes', y, mode + shape(lanes, mirror))
            bt = sum(l < 4 for l in lanes)
            for label, flag in [('3plus-BT', bt >= 3), ('4-BT', bt == 4),
                                ('same-side-BT-FX', (4 in lanes and (0 in lanes or 1 in lanes)) or
                                 (5 in lanes and (2 in lanes or 3 in lanes))),
                                ('FX+two-home-BT', {0, 1, 4} <= set(lanes) or {2, 3, 5} <= set(lanes))]:
                if flag:
                    counters['chord-shapes'][mode + 'flag:' + label] += 1
        if sum(turning) == 1:
            side = turning.index(True)
            for lane in lanes:
                norm = (3, 2, 1, 0, 5, 4)[lane] if side else lane
                if norm in (0, 4):
                    add('knob-crossing-press', y, NAMES[norm])
        if all(turning):
            add('both-knobs-and-button', y, 'shape:' + shape(lanes))
            for l in lanes:
                counters['both-knobs-and-button']['lane:' + NAMES[l]] += 1
        for a, b, held in active:
            for chip, length in starts[y]:
                if length or held == chip:
                    continue
                side = home(held)
                fits = _hands_for_buttons(pressed_lanes([held, chip])) == 1
                same = home(chip) == side
                if same or (fits and busy_at(1 - side, y)):
                    add('hold-and-chip', y, 'reach:hold-' + NAMES[held] + '+chip-' + NAMES[chip])
                elif not fits and busy_at(1 - side, y):
                    add('hold-and-chip', y, 'leave:hold-' + NAMES[held] + '+chip-' + NAMES[chip], rank=-1)
                if held >= 4 and chip < 4 and same:
                    add('fx-long-with-bt-chips', y, 'hold-' + NAMES[held] + '+chip-' + NAMES[chip])
        active.extend((y, y + length, l) for l, length in starts[y] if length)

    # Slam-related counts are pairs with a slam, so a double slam can count twice.
    for side in (0, 1):
        for (a, _, _), (b, _, _) in zip(slams[side], slams[side][1:]):
            dt = ms(a, b)
            add('slam-interval', b, 'LR'[side], 'interval_ms', dt, dt)
        for y, direction, start in slams[side]:
            if y - start < 15:
                counters['slam-interval']['near_section_start'] += 1
                sample('slam-interval', 'section_start_ms', ms(start, y))
            if y in starts:
                lanes = [l for l, _ in starts[y]]
                direction *= -1 if side else 1
                add('slam-with-button', y, 'L:' + ('right:' if direction > 0 else 'left:') + shape(lanes, side == 1))
            for b in ys[bisect_right(ys, y):bisect_right(ys, y + 15)]:
                for l, _ in starts[b]:
                    if home(l) == side:
                        add('button-during-slam-same-hand', b, NAMES[l], 'delay_ms', ms(y, b), ms(y, b))
        for start, end, points, w in sections[side]:
            if w == 2:
                add('wide-laser', start, 'LR'[side], 'duration_ms', ms(start, end), -ms(start, end))
            direction, reversals = 0, []
            for (a, v, vf, _), (b, vb, _, _) in zip(points, points[1:]):
                if v != vf:
                    direction, reversals = 0, []
                d = (vb > vf) - (vb < vf)
                if d:
                    if direction and d != direction:
                        add('laser-zigzag', a, 'LR'[side])
                        if reversals:
                            dt = ms(reversals[-1], a)
                            sample('laser-zigzag', 'reversal_interval_ms', dt)
                        reversals.append(a)
                    direction = d
        for prev, nxt in zip(sections[side], sections[side][1:]):
            a, b = prev[1], nxt[0]
            last = 0.5 + (prev[2][-1][2] - 0.5) * prev[3]
            first = 0.5 + (nxt[2][0][1] - 0.5) * nxt[3]
            if abs(last - first) > 0.25 and b >= a:
                add('laser-gap', b, 'LR'[side], 'gap_ms', ms(a, b), ms(a, b))
    rev = metrics['laser-zigzag']['reversal_interval_ms']
    if rev:
        sample('laser-zigzag', 'chart_min_reversal_ms', min(rev))

    crossed = crossing_ranges(segments)
    section_starts = [[s[0] for s in lane] for lane in sections]
    point_ys = [[tuple(p[0] for p in s[2]) for s in lane] for lane in sections]

    def position(side, y):
        i = bisect_right(section_starts[side], y) - 1
        if i < 0 or y > sections[side][i][1]:
            return None
        _, _, pts, w = sections[side][i]
        j = bisect_right(point_ys[side][i], y) - 1
        a, _, v, curve = pts[j]
        if j + 1 < len(pts):
            b, vb, _, _ = pts[j + 1]
            v += (vb - v) * curve_at(curve, (y - a) / (b - a))
        return 0.5 + (v - 0.5) * w

    # An isolated section endpoint or post-slam value can cross for zero time.
    boundaries = sorted({p[0] for lane in sections for s in lane for p in s[2]})
    for y in boundaries:
        l, r = position(0, y), position(1, y)
        if l is not None and r is not None and l > r and not any(a <= y <= b for a, b in crossed):
            crossed.append([y, y])
    crossed.sort()
    for a, b in crossed:
        dt = ms(a, b)
        add('laser-crossing', a, 'episode', 'duration_ms', dt, -dt)
    for y in ys:
        l, r = position(0, y), position(1, y)
        if l is not None and r is not None and l > r:
            counters['laser-crossing']['button_start_times'] += 1
            counters['laser-crossing']['button_starts'] += len(starts[y])
    counters['laser-crossing']['zero_duration_episodes'] = sum(a == b for a, b in crossed)

    for y, lane, length in events:
        if length:
            sample('short-long', 'all_long_beats', length / 240)
            if length < 30:
                add('short-long', y, 'BT' if lane < 4 else 'FX', 'short_beats', length / 240, length)
        if y % 60 and y % 80:
            grid = '1/' + str(960 // math.gcd(960, y))
            add('offgrid', y, grid)
    end = max([0, *(y + length for y, _, length in events), *(s[1] for lane in sections for s in lane)])
    measures = timing.pulse_to_measure(end)[0] + 1
    for rule, row in result.items():
        row['by'] = dict(sorted(counters[rule].items()))
        row['metrics'] = dict(metrics[rule])
        row['examples'] = examples[rule]
    return {'measures': measures, 'button_starts': len(events),
            'curve_points': sum(p[3][0] != p[3][1] for lane in sections for s in lane for p in s[2]),
            'longs': len(longs), 'laser_sections': sum(map(len, sections)), 'rules': result}


def sources():
    raw = [json.loads(s) for s in (ROOT / 'out' / 'sdvxin_stats.jsonl').read_text(encoding='utf-8').splitlines()]
    # Same key may occur more than once in a growing cache: last row wins.
    raw = list({r['key']: r for r in raw}.values())
    tasks, issues = [], []
    for row in raw:
        if not usable(row):
            continue
        level = int(row['level'])
        if level not in (17, 18, 19, 20):
            continue
        path = ROOT / 'out' / 'sdvxin_kson' / (row['key'] + '.json')
        meta = {'key': row['key'], 'title': row['title'], 'level': row['level'],
                'group': str(level) if level < 19 else '19-20'}
        if not path.exists():
            issues.append({**meta, 'error': 'missing decoded KSON'})
        else:
            tasks.append((str(path), meta))
    for path in sorted((ROOT / 'corpus' / 'official').rglob('*.ksh')):
        key = 'ksm:' + path.relative_to(ROOT / 'corpus' / 'official').as_posix()
        tasks.append((str(path), {'key': key, 'group': 'ksm', 'file': path.name}))
    return tasks, {'stats_rows': len(raw), 'stats_decode_errors': sum('error' in r for r in raw),
                   'stats_rejected': sum(not usable(r) for r in raw), 'source_issues': issues}


def cache_version():
    paths = [Path(__file__), ROOT / 'src' / 'ksmauto' / 'lint.py', ROOT / 'src' / 'ksmauto' / 'timing.py',
             ROOT / 'src' / 'ksmauto' / 'ksh.py', Path(__file__).with_name('sdvxin_stats.py')]
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def fingerprint(path, meta, version):
    st = Path(path).stat()
    return [version, st.st_size, st.st_mtime_ns, meta]


def mine(task):
    path, meta, stamp = task
    try:
        chart = load_ksh(path) if path.endswith('.ksh') else json.loads(Path(path).read_text(encoding='utf-8'))
        meta = {**meta, 'title': meta.get('title', chart.get('meta', {}).get('title', '')),
                'level': meta.get('level', chart.get('meta', {}).get('level'))}
        return {'meta': meta, 'fingerprint': stamp, 'tally': tally(chart)}
    except Exception as exc:  # noqa: BLE001 - an input failure must not hide other charts
        return {'meta': meta, 'fingerprint': stamp, 'error': repr(exc)}


def verdict(count, charts, measures, n, seen_anywhere):
    if not seen_anywhere:
        return 'never'
    if count * 100 / max(measures, 1) < 1 or charts / max(n, 1) < 0.05:
        return 'rare'
    return 'common'


def aggregate(rows):
    table, groups = {}, {}
    for group in GROUPS:
        rr = [r for r in rows if r['meta']['group'] == group and 'error' not in r]
        groups[group] = {'charts': len(rr), 'measures': sum(r['tally']['measures'] for r in rr),
                         'curve_charts': sum(bool(r['tally']['curve_points']) for r in rr),
                         'levels': dict(sorted(Counter(str(r['meta']['level']) for r in rr).items(), key=lambda kv: float(kv[0])))}
    for rule in (*RULES, 'jack-mixed'):
        by_group = {}
        for group in GROUPS:
            rr = [r for r in rows if r['meta']['group'] == group and 'error' not in r]
            counts, samples, ex = Counter(), defaultdict(list), []
            n = charts = 0
            for r in rr:
                t = r['tally']['rules'][rule]
                n += t['count']
                charts += bool(t['count'])
                counts.update(t['by'])
                for k, vals in t['metrics'].items():
                    samples[k].extend(vals)
                for e in t['examples']:
                    ex.append({**r['meta'], **e})
            ex.sort(key=lambda e: (e['rank'], e['key'], e['measure']))
            picked = []
            for e in ex:
                if not any(p['key'] == e['key'] and p['measure'] == e['measure'] for p in picked):
                    picked.append({k: v for k, v in e.items() if k != 'rank'})
                if len(picked) == 5:
                    break
            by_group[group] = {
                'occurrences': n, 'charts_with_occurrence': charts,
                'per_100_measures': round(100 * n / max(groups[group]['measures'], 1), 6),
                'chart_percent': round(100 * charts / max(len(rr), 1), 6), 'by': dict(sorted(counts.items())),
                'metrics': {k: quantiles(v, duration=('duration' in k or 'beats' in k or 'run_hits' in k or 'stream16' in k),
                                         chart=rule == 'stream-density' or k.startswith('chart_longest')) for k, v in samples.items()},
                'examples': picked,
            }
            if rule == 'laser-crossing':
                by_group[group]['total_duration_sec'] = round(sum(samples['duration_ms']) / 1000, 6)
            if rule == 'fx-long-with-bt-chips':
                by_group[group]['per_100_button_starts'] = round(100 * n / max(sum(r['tally']['button_starts'] for r in rr), 1), 6)
        seen = any(g['occurrences'] for g in by_group.values())
        for group, g in by_group.items():
            g['verdict'] = verdict(g['occurrences'], g['charts_with_occurrence'], groups[group]['measures'], groups[group]['charts'], seen)
        table[rule] = by_group
    return {'groups': groups, 'rules': table}


def number(x):
    return f'{x:,.3f}'.rstrip('0').rstrip('.')


def metric_text(row):
    parts = []
    for name, d in row['metrics'].items():
        if not d['n']:
            continue
        labels = ('p50', 'p99', 'max') if name.startswith(('peak_', 'chart_longest')) or name == 'stream16_max_sec' else (
            ('max', 'p99', 'p99.9') if any(k in name for k in ('duration', 'beats', 'run_hits')) else ('min', 'p0.1', 'p1', 'p5', 'p50'))
        parts.append(name + ' [' + '/'.join(number(d[k]) for k in labels) + ']')
    return '<br>'.join(parts) or '—'


def locations(examples, n=3):
    # Keep prose examples to title and measure only. No source chart fragments.
    picked = []
    for e in examples:
        if not any(p['key'] == e['key'] for p in picked):
            picked.append(e)
    for e in examples:
        if not any((p['key'], p['measure']) == (e['key'], e['measure']) for p in picked):
            picked.append(e)
    return '、'.join(f'「{e["title"].replace("|", "／")}」m{e["measure"]}' for e in picked[:n]) or '該当なし'


def write_doc(report, path):
    lines = ['# 公式譜面の配置採掘（phase 1）', '',
             '左手＝L つまみ・FL・BT A/B、右手＝R つまみ・FR・BT C/D を基本とする。'
             'つまみの「操作中」は `lint._moving_laser_ranges`（傾斜、直角の前30〜後31 pulse未満）。'
             '自側 long の保持も手を占有する。片つまみ中は空いた手が全レーンを担当できるが、'
             '同時押しの必要手数は `_hands_for_buttons`（隣接2位置、FL は B、FR は C の位置）による。', '',
             'ジャックは基本の担当手を用い、その手が全区間つまみ中かつ反対つまみが空なら担当を反転する。'
             '反対手の連続占有が区間全体を覆えば片手、占有も区間途中の自側打鍵もなければ両手。'
             '部分的な占有・途中の自側打鍵だけのものは mixed として別集計する。実際の運指を断定するものではない。', '',
             '小節は `TimingMap` の **0 始まり**。分母は pulse 0 から最後のボタン終端／レーザー端を含む小節まで（空小節も含む）。'
             '時間は BPM 変化を積分し、音源 offset は用いない。占有区間は半開区間。'
             'hold-and-chip と既存 lint の保持判定だけは保持開始の同時刻も除く。'
             '1 拍＝240 pulse。grid の 1/16・1/12 は全音符基準（60・80 pulse）、'
             '「1/16 拍後」は15 pulse、「1/8 拍未満」は30 pulse と区別する。', '',
             '判定は全群で0なら **never**、それ以外は各群で100小節あたり1未満 **または** 出現譜面率5%未満なら **rare**、残りは **common**。'
             'ある群だけ0の場合は rare。これは出現頻度の仮判定であり、許可／禁止の結論ではない。'
             '間隔に上限を置かないため、jack の common は高速連打の許容を意味しない。', '',
             '表の頻度＝「出現数 / 該当譜面数（%） / 100小節あたり」。'
             '間隔の分布＝[min/p0.1/p1/p5/p50] ms、長さ＝[max/p99/p99.9]、'
             '譜面別最大密度・stream16・最長trill＝[p50/p99/max]。分位点は線形補間。', '',
             '| 群 | 譜面数 | 小節数 | レベル（譜面数） |', '|---|---:|---:|---|']
    for group, g in report['groups'].items():
        levels = '、'.join(f'{k}: {v}' for k, v in g['levels'].items())
        lines.append(f'| {group} | {g["charts"]} | {g["measures"]:,} | {levels} |')
    d = report['inputs']
    lines += ['', f'SDVX: {d["stats_rows"]} 統計行中 usable 不適合 {d["stats_rejected"]}（元 decode エラー {d["stats_decode_errors"]} を含む）。'
              f'採掘時エラー／欠落 {len(report["errors"])} 件。曲線レーザー採用 {sum(g["curve_charts"] for g in report["groups"].values())} 譜面。'
              'usable は chip 数・最高 BPM の検査であり、レーザー・long の転記精度までは保証しない。KSM は別群で集計する。', '',
              '再現: `uv run python tests/eval/placement_rules.py`。'
              '入力のサイズ・mtime、コード、メタ情報が変わるとキャッシュを無効化する。'
              '全形状・レーン内訳・群ごと最大5例は `out/placement_rules.json`、譜面別キャッシュは '
              '`out/placement_rules_cache.jsonl`（どちらもローカル専用）。', '']
    for idx, (rule, definition) in enumerate(RULES.items(), 1):
        lines += [f'## {idx}. {rule}', '', '| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |',
                  '|---|---|---|---|---|---|']
        for group, row in report['rules'][rule].items():
            by = row['by']
            extra = []
            if rule == 'hand-overload':
                extra.extend(f'{k}: {v:,}' for k, v in by.items() if k.startswith('cause:'))
            elif rule in ('jack-one-hand', 'jack-two-hand', 'long-end-to-chip'):
                extra.append(f'<75ms: {by.get("under_75ms", 0):,}')
            elif rule == 'slam-interval':
                extra.append(f'開始後<15pulse: {by.get("near_section_start", 0):,}')
            elif rule == 'laser-crossing':
                extra.append(f'合計 {number(row["total_duration_sec"])}秒、開始 {by.get("button_start_times", 0):,}時刻/{by.get("button_starts", 0):,}ボタン')
            elif rule == 'hold-and-chip':
                extra.append('leave: ' + str(sum(v for k, v in by.items() if k.startswith('leave:'))))
            elif rule == 'fx-long-with-bt-chips':
                extra.append('100ボタン開始あたり ' + number(row['per_100_button_starts']))
            elif rule == 'chord-shapes':
                extra.extend(f'{k}: {v:,}' for k, v in by.items() if ':flag:' in k)
            elif rule in ('offgrid', 'knob-crossing-press', 'both-knobs-and-button'):
                extra.extend(f'{k}: {v:,}' for k, v in by.items() if not k.startswith('shape:'))
            frequency = f'{row["occurrences"]:,} / {row["charts_with_occurrence"]} ({row["chart_percent"]:.1f}%) / {number(row["per_100_measures"])}'
            detail = '<br>'.join([metric_text(row), *extra])
            lines.append(f'| {rule} | {definition} | {group} | {frequency} | {detail} | {row["verdict"]} |')
        ex = [e for g in report['rules'][rule].values() for e in g['examples']]
        lines += ['', '例: ' + locations(ex), '']
    lines += ['## 分類と読み方の補足', '',
              '- trill は単独 chip の交互列が3打以上。担当手の他の開始・同時押し・担当側のつまみで切る。'
              'AB/CD は自側の手、BC はどちらの手でも調べる。間隔の上限は置かない。',
              '- 密度窓は `(t−W,t]`、曲端でも W 秒で割る。stream16 は既存 `stats()` の値をそのまま用いる。',
              '- 和音表は long 開始も含む。全形状はローカル JSON に保存。3+BT と4BT、同側BT+FXのフラグは重複する。'
              '片つまみ・直角は操作つまみを左に反転し、直角の向きも反転する。',
              '- 交差は幅2を中心から2倍に拡大した表示座標で、線形補間の交点を解く。曲線は既存プレビューと同じ2次 Bézier。'
              '交点計算では表示位置誤差 1e-9 幅以内の折れ線へ細分化し、ボタン時刻の位置は曲線式で直接評価する。'
              '直角後の値も評価し、瞬間だけの交差は長さ0の区間とする。',
              '- hold-and-chip は保持開始・終端と同時刻を除く。自側の他レーン、または反対手占有中に隣接2位置へ収まる組を reach、'
              '反対手占有中に2位置を超える組を leave とする。保持手の実際の持ち替えは推測しない。',
              '- short-long は全 long の拍数分布と、30 pulse 未満だけの分布を併記する。offgrid の 1/N は '
              '`N=960/gcd(960,pulse)` の既約全音符分母（絶対 pulse 基準）。', '',
              'jack-mixed（主表の2分類に入らない区間）:', '',
              '| 群 | 出現数 | 譜面数 | 100小節あたり |', '|---|---:|---:|---:|']
    for group, row in report['rules']['jack-mixed'].items():
        lines.append(f'| {group} | {row["occurrences"]:,} | {row["charts_with_occurrence"]} | {number(row["per_100_measures"])} |')
    lines += ['', '## 判断が割れそうなもの', '', *surprises(report), '']
    path.write_text('\n'.join(lines), encoding='utf-8')


def surprises(report):
    """Concise review prompts, backed by the same bounded locations as the table."""
    lines = []
    for rule, text in (
        ('hand-overload', 'ほぼ0という予想に反して多い。直角前後の占有余白だけによる件数を主表で分離した'),
        ('jack-mixed', '途中だけ占有される区間は片手／両手へ無理に二分できない'),
        ('jack-one-hand', '短い間隔でも担当手は推定。反対側つまみ・long の連続占有と実際の運指は区別したい'),
        ('hold-and-chip', 'leave は固定の保持手を仮定した結果で、持ち替え・つまみ余白の影響があり得る'),
        ('button-during-slam-same-hand', '直角の直後にホーム側の開始があっても、反対手で拾う運指はあり得る'),
        ('laser-crossing', '見た目の交差と手の交差は別。幅2・瞬間だけの交差も含む'),
        ('short-long', '1/8拍未満は高難度群だけに少数見つかる。最低値だけで禁止閾値を決めない'),
        ('stream-density', '出現単位が譜面なので100小節あたりの機械判定は曲長に依存する。rareでも密度の配置が稀とはいえない'),
    ):
        rr = report['rules'][rule]
        n = sum(r['occurrences'] for r in rr.values())
        if not n:
            continue
        examples = [e for r in rr.values() for e in r['examples']]
        if rule == 'hold-and-chip':
            n = sum(v for r in rr.values() for k, v in r['by'].items() if k.startswith('leave:'))
            examples = [e for e in examples if e['detail'].startswith('leave:')]
        lines.append(f'- **{rule}**: {text}（{n:,}件）。例: {locations(examples)}。')
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument('--refresh', action='store_true', help='ignore per-chart cache')
    args = parser.parse_args()
    start = time.perf_counter()
    tasks, inputs = sources()
    version = cache_version()
    cached = {}
    if CACHE.exists() and not args.refresh:
        for line in CACHE.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # tolerate an interrupted final append
            cached[row['meta']['key']] = row
    results, pending = [], []
    for path, meta in tasks:
        stamp = fingerprint(path, meta, version)
        old = cached.get(meta['key'])
        if old and old.get('fingerprint') == stamp and 'error' not in old:
            results.append(old)
        else:
            pending.append((path, meta, stamp))
    reused = len(results)
    print(f'{len(tasks)} inputs, {reused} cached, {len(pending)} to mine', flush=True)
    CACHE.parent.mkdir(exist_ok=True)
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as pool, CACHE.open('a', encoding='utf-8') as out:
            for i, row in enumerate(pool.map(mine, pending, chunksize=4), 1):
                results.append(row)
                out.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
                if i % 50 == 0 or i == len(pending):
                    out.flush()
                    print(f'{i}/{len(pending)} mined ({time.perf_counter() - start:.1f}s)', flush=True)
    # Compact old versions and duplicates only after a successful run.
    tmp = CACHE.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as out:
        for row in results:
            out.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    tmp.replace(CACHE)
    report = aggregate(results)
    report['inputs'] = inputs
    report['errors'] = inputs['source_issues'] + [r for r in results if 'error' in r]
    report['runtime_sec'] = round(time.perf_counter() - start, 3)
    report['cache_reused'] = reused
    (ROOT / 'out' / 'placement_rules.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_doc(report, ROOT / 'docs' / 'placement-rules.md')
    print(f'Finished in {time.perf_counter() - start:.2f}s; {len(report["errors"])} mining errors', flush=True)
    for group, g in report['groups'].items():
        print(f'{group}: {g["charts"]} charts, {g["measures"]} measures')
    for error in report['errors'][:10]:
        print('error:', error)


if __name__ == '__main__':
    main()
