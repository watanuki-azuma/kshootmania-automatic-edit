"""Tally note placement patterns in the local sdvx.in corpus (local use only).

Reads the charts that sdvxin_stats.py marks usable, decoding each once into
out/sdvxin_kson/<key>.json, and prints per level group:
  - which lanes the free hand presses while one knob turns (mirrored so the
    turning knob is always on the left),
  - the set of lanes one knob-turning span uses,
  - chord shapes and sixteenth-run motifs without a turning knob.

Usage: uv run python tests/eval/sdvxin_patterns.py [corpus/sdvxin_full]
       uv run python tests/eval/sdvxin_patterns.py --chart work/chart.kson  (same tallies for one chart)
"""

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ksmauto.lint import _button_events, _moving_laser_ranges, lint
from ksmauto.sdvxin import load_sdvxin
from sdvxin_stats import CACHE, usable

ROOT = Path(__file__).resolve().parents[2]
KSON_DIR = ROOT / 'out' / 'sdvxin_kson'
GROUPS = {17: '17', 18: '18', 19: '19-20', 20: '19-20'}
# Lanes as seen with the turning knob on the left: FX-L sits under A/B, FX-R under C/D.
NAMES = ('A', 'B', 'C', 'D', 'FL', 'FR')


def decode(chart_dir):
    out = KSON_DIR / f'{chart_dir.name}.json'
    if not out.exists():
        out.write_text(json.dumps(load_sdvxin(chart_dir)), encoding='utf-8')
    return chart_dir.name


def merged(ranges):
    spans = []
    for a, b in sorted(ranges):
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return spans


def lane_name(kind, lane, mirror):
    if kind == 'fx':
        return NAMES[4 + (1 - lane if mirror else lane)]
    return NAMES[3 - lane if mirror else lane]


def tally(chart, t):
    lasers = chart['note'].get('laser', [[], []])
    spans = [merged(_moving_laser_ranges({'note': {'laser': [side]}})) for side in lasers]
    chips = sorted((y, kind, lane) for kind, lane, y, _ in _button_events(chart))
    by_y = defaultdict(list)
    for y, kind, lane in chips:
        by_y[y].append((kind, lane))

    def turning(y):
        return [any(a <= y < b for a, b in s) for s in spans]

    # Free hand under one turning knob.
    for side in (0, 1):
        for a, b in spans[side]:
            used = set()
            for y in sorted(k for k in by_y if a <= k < b):
                if turning(y)[1 - side]:
                    continue
                names = tuple(sorted(lane_name(k, l, side == 1) for k, l in by_y[y]))
                for n in names:
                    t['knob_lane'][n] += 1
                t['knob_chord'][' '.join(names)] += 1
                used.update(names)
            if used:
                t['knob_span'][''.join(sorted(used, key=NAMES.index))] += 1
    t['both_turning']['chip timings'] += sum(1 for y in by_y if all(turning(y)))
    t['lint']['chips'] += len(chips)
    for finding in lint(chart):
        t['lint'][finding.rule] += 1
    # No turning knob: chord shapes and sixteenth-run motifs (BT only).
    run = []
    for y in sorted(by_y):
        if any(turning(y)):
            run = []
            continue
        names = tuple(sorted(lane_name(k, l, False) for k, l in by_y[y]))
        t['free_chord'][' '.join(names)] += 1
        bt = [l for k, l in by_y[y] if k == 'bt']
        if len(bt) != 1 or len(by_y[y]) != 1 or (run and y - run[-1][0] > 60):
            run = []
        if len(bt) == 1 and len(by_y[y]) == 1:
            run.append((y, bt[0]))
            if len(run) >= 4:
                t['motif'][''.join(NAMES[l] for _, l in run[-4:])] += 1


def show(title, counter, top=12):
    total = sum(counter.values()) or 1
    items = ', '.join(f'{k or "-"} {100 * v / total:.1f}%' for k, v in counter.most_common(top))
    print(f'  {title}: {items}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=ROOT / 'corpus' / 'sdvxin_full')
    parser.add_argument('--chart', type=Path, help='tally one KSON chart instead of the corpus')
    args = parser.parse_args()
    if args.chart:
        t = defaultdict(Counter)
        tally(json.loads(args.chart.read_text(encoding='utf-8')), t)
        report(args.chart.name, t)
        return
    rows = [json.loads(line) for line in CACHE.read_text(encoding='utf-8').splitlines()]
    rows = {r['key']: r for r in rows if usable(r)}
    KSON_DIR.mkdir(parents=True, exist_ok=True)
    dirs = [p.parent for p in sorted(args.root.glob('*/*/meta.json')) if p.parent.name in rows]
    with ProcessPoolExecutor() as pool:
        list(pool.map(decode, dirs, chunksize=4))
    tallies = defaultdict(lambda: defaultdict(Counter))
    for key, row in rows.items():
        path = KSON_DIR / f'{key}.json'
        if path.exists():
            tally(json.loads(path.read_text(encoding='utf-8')), tallies[GROUPS[int(row['level'])]])
    for group in ('17', '18', '19-20'):
        report(f'Lv{group}', tallies[group])


def report(title, t):
    print(title)
    show('free hand lane while the left knob turns', t['knob_lane'])
    show('chords while the left knob turns', t['knob_chord'])
    show('lanes used over one turning span', t['knob_span'], 15)
    chips = t['lint']['chips'] or 1
    print(f'  chip timings with both knobs turning: {t["both_turning"]["chip timings"] / chips * 1000:.1f} per 1000 chips')
    print('  lint findings per 1000 chips: ' + ', '.join(
        f'{k} {v / chips * 1000:.1f}' for k, v in t['lint'].most_common() if k != 'chips'))
    show('chords, no knob turning', t['free_chord'], 15)
    show('4-note sixteenth motifs, no knob turning', t['motif'], 20)


if __name__ == '__main__':
    main()
