"""Decode a local sdvx.in corpus and summarise chart statistics per level (local use only).

Results are cached in out/sdvxin_stats.jsonl (one line per chart, keyed by chart key),
so re-running after more charts are fetched only decodes the new ones.

Usage: uv run python tests/eval/sdvxin_stats.py [corpus/sdvxin_full ...]
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from ksmauto.lint import stats
from ksmauto.sdvxin import load_sdvxin, sdvx_counts

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'out' / 'sdvxin_stats.jsonl'
SUMMARY = ('avg_nps', 'peak_nps', 'laser_ratio', 'slams', 'chord_ratio', 'stream16_max_sec',
           'knob_move_ratio', 'knob_button_ratio', 'long_ratio', 'duration_sec')


def load_rows(roots):
    cached = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            cached[row['key']] = row
    new = 0
    with CACHE.open('a', encoding='utf-8') as out:
        for root in roots:
            for path in sorted(Path(root).glob('*/*/meta.json')):
                meta = json.loads(path.read_text(encoding='utf-8'))
                if meta['key'] in cached:
                    continue
                try:
                    chart = load_sdvxin(path.parent)
                    row = {'key': meta['key'], 'level': float(meta['level']), 'kind': meta['kind'],
                           'title': meta['title'], 'stats': stats(chart), 'decoded': sdvx_counts(chart),
                           'official': {k: int(meta['counts'][k] or 0) for k in ('chip', 'hold', 'laser')}}
                except Exception as exc:  # noqa: BLE001 - report and keep going over the corpus
                    row = {'key': meta['key'], 'level': float(meta['level']), 'error': repr(exc)}
                cached[row['key']] = row
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                new += 1
    return list(cached.values()), new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='*', type=Path, default=[ROOT / 'corpus' / 'sdvxin_full'])
    args = parser.parse_args()
    CACHE.parent.mkdir(exist_ok=True)
    rows, new = load_rows(args.roots)
    errors = [r for r in rows if 'error' in r]
    good = [r for r in rows if 'error' not in r]
    chip_ok = sum(r['decoded']['chip'] == r['official']['chip'] for r in good)
    chip_close = sum(abs(r['decoded']['chip'] - r['official']['chip']) <= max(3, 0.005 * r['official']['chip'])
                     for r in good)
    print(f'{len(rows)} charts ({new} new), {len(errors)} failed to decode; '
          f'chip exact {chip_ok}/{len(good)}, within 0.5% {chip_close}/{len(good)}')
    for r in errors[:10]:
        print('  error', r['key'], r['error'])
    by_level = defaultdict(list)
    for r in good:
        # Only trust charts whose chip count shows the decode is sound.
        if abs(r['decoded']['chip'] - r['official']['chip']) <= max(3, 0.005 * r['official']['chip']):
            by_level[int(r['level'])].append(r['stats'])
    print('level  n  ' + '  '.join(f'{k:>10}' for k in SUMMARY))
    for level in sorted(by_level):
        group = by_level[level]
        med = [statistics.median(s[k] for s in group) for k in SUMMARY]
        print(f'{level:>5} {len(group):>3}  ' + '  '.join(f'{v:>10.2f}' for v in med))


if __name__ == '__main__':
    main()
