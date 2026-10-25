"""Physical hand categories and review output; per-chart evidence stays in out/."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ksmauto.ksh import load_ksh
from ksmauto.lint import (JACK_BANDS_MS, button_categories, effective_hands,
                          jack_band, jack_intervals, jack_key, laser_demands, lint)
from ksmauto.timing import TimingMap

GROUPS = ('17', '18', '19-20', 'ksm')
JACK_CLASSES = ('two-hand', 'assisted', 'one-hand')


def load_chart(path, meta):
    c = load_ksh(path) if path.endswith('.ksh') else json.loads(Path(path).read_text(encoding='utf-8'))
    # The decoder floors levels; use the source's decimal level for this audit.
    if meta['group'] != 'ksm':
        c.setdefault('meta', {})['level'] = meta['level']
    return c


def chart_evidence(chart, thresholds):
    timing = TimingMap(chart['beat'])
    profiles = laser_demands(chart, timing)
    categories, examples = Counter(), {}
    for y, key, _, _ in button_categories(chart, timing, thresholds, profiles):
        categories[key] += 1
        examples.setdefault(key, timing.pulse_to_measure(y)[0])
    jacks = []
    for lane, a, b, length, cls in jack_intervals(chart, timing, thresholds, profiles):
        jacks.append([cls, 'BT' if lane < 4 else 'FX',
                      (timing.pulse_to_sec(b) - timing.pulse_to_sec(a)) * 1000,
                      timing.pulse_to_measure(b)[0]])
    return {'categories': dict(categories), 'examples': examples, 'jacks': jacks}


def percentile(values, p):
    v = sorted(values)
    if not v:
        return None
    x = (len(v) - 1) * p
    a, b = math.floor(x), math.ceil(x)
    return v[a] + (v[b] - v[a]) * (x - a)


def build_policy(rows, thresholds):
    groups = {g: {'charts': 0, 'measures': 0} for g in GROUPS}
    categories = defaultdict(lambda: defaultdict(Counter))
    samples, bands, band_charts = defaultdict(list), Counter(), Counter()
    for row in rows:
        if 'error' in row:
            continue
        g = row['meta']['group']
        groups[g]['charts'] += 1
        groups[g]['measures'] += row['tally']['measures']
        for key, n in row['hand']['categories'].items():
            categories[key][g].update(count=n, charts=1)
        seen = set()
        for cls, kind, dt, _ in row['hand']['jacks']:
            cls = 'one-hand' if cls == 'mixed' else cls
            samples[g, cls, kind].append(dt)
            tag = (g, cls, kind, jack_band(dt))
            bands[tag] += 1
            seen.add(tag)
        band_charts.update(seen)
    jack = {}
    for g in GROUPS:
        jack[g] = {}
        for cls in JACK_CLASSES:
            jack[g][cls] = {}
            for kind in ('BT', 'FX'):
                bins = [{'count': bands[g, cls, kind, i], 'charts': band_charts[g, cls, kind, i],
                         'per_100_measures': bands[g, cls, kind, i] * 100 / max(groups[g]['measures'], 1)}
                        for i in range(len(JACK_BANDS_MS))]
                jack[g][cls][kind] = {
                    'count': len(samples[g, cls, kind]),
                    'p1_ms': percentile(samples[g, cls, kind], .01),
                    'robust_min_ms': next((bound for bound, b in zip(JACK_BANDS_MS, bins)
                                           if b['charts'] >= 5), None),
                    'bands': bins}
    return {'version': 2, 'rare_per_100_measures': 0.05, 'thresholds': thresholds,
            'groups': groups, 'jack_bands_ms': list(JACK_BANDS_MS),
            'categories': {k: {g: {'count': v[g]['count'], 'charts': v[g]['charts'],
                                  'per_100_measures': v[g]['count'] * 100 / max(groups[g]['measures'], 1)}
                              for g in GROUPS} for k, v in sorted(categories.items())}, 'jacks': jack}


def review_rows(rows, policy):
    examples = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if 'error' in row:
            continue
        for key, m in row['hand']['examples'].items():
            selected = examples[key][row['meta']['group']]
            sample = (row['meta']['title'], m)
            if len(selected) < 3 and sample not in selected:
                selected.append(sample)
    return [(key, groups, examples[key]) for key, groups in policy['categories'].items()
            if effective_hands(key) > 2]


def write_review(rows, policy, path):
    lines = ['# 配置の人手レビュー', '',
             '開始時刻のボタン集合（開始＋保持中、終端は除く）を物理カテゴリで集約。'
             '片手は BT の連続3レーン A–C または B–D と、その窓に下側2レーンが収まる FX を覆う'
             '（A–C は FX-L、B–D は FX-R）。左右の手はどちらの窓にも移動できる。'
             '必要手数は最小被覆。実効手数＝ボタン手数＋slam/steep 各1＋gentle/ending 各0.5。'
             'ending は移動終点まで50 ms以内、steep は32通常幅/秒超。', '',
             'この被覆モデルでは全6ボタンを両窓で覆えるため、ボタンだけで3手以上になる集合はない。'
             '例の A+D+両FX は A+FX-L と D+FX-R の2手になる。追加の運指制約は仮定しない。', '',
             'キーは `左需要,右需要|ボタン手数|home/crossing`。需要の強い側を左へ反転。'
             'crossing は1手で押す際、需要の軽い側の手を使うには自側の窓を越える必要があること。'
             '2手のボタンは両手を必要とし、busy なつまみ側の手も必要になる。'
             '各群のセルは「件数 / 譜面数 / 100小節あたり」。例は曲名と0始まりの小節、群ごと最大3件。'
             '表は観測された実効手数>2の全カテゴリ。判断は人が記入する。', '',
             '`src/ksmauto/data/placement_verdicts.json` に表のキーを写し、`"allow"` は頻度検査を抑制、'
             '`"forbid"` は `placement-forbidden` warning、`{"min_level": 18}` は18未満で '
             '`placement-min-level` warning（18以上は抑制）。判定があれば実効手数・頻度・ジャック閾値より優先。'
             '初期値は空。ジャックは各群の行キーを使い、その行の全反復に適用する。', '',
             '| カテゴリキー | 実効手数 | 17 | 18 | 19-20 | ksm | 例（群ごと最大3） | 判断 |',
             '|---|---:|---|---|---|---|---|---|']
    for key, groups, examples in review_rows(rows, policy):
        cells = [f'{groups[g]["count"]} / {groups[g]["charts"]} / {groups[g]["per_100_measures"]:.5f}' for g in GROUPS]
        ex = '<br>'.join(g + ': ' + '、'.join(f'「{title.replace("|", "／")}」m{m}' for title, m in examples[g])
                         for g in GROUPS if examples[g])
        lines.append(f'| {key.replace("|", "&#124;")} | {effective_hands(key):g} | ' + ' | '.join(cells) + f' | {ex} | 未判定 |')
    lines += ['', 'ジャックは mixed を one-hand に合算。各時間帯セルは100小節あたり、'
              'p1 は従来の1パーセンタイル（ms）。警告下限は同群の5譜面以上に現れた最短帯の下端。'
              '帯は左端を含み右端を含まない。120 ms以上も下限導出のため集計する。', '',
              '| 行キー | <60 | 60–70 | 70–80 | 80–90 | 90–100 | 100–120 ms | p1 ms | 警告下限 ms | 判断 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for g in GROUPS:
        for cls in JACK_CLASSES:
            for kind in ('BT', 'FX'):
                row = policy['jacks'][g][cls][kind]
                cells = [f'{b["per_100_measures"]:.3f}' for b in row['bands'][:6]]
                cells += ['—' if row[k] is None else f'{row[k]:.3f}' for k in ('p1_ms', 'robust_min_ms')]
                lines.append(f'| {jack_key(g, cls, kind)} | ' + ' | '.join(cells) + ' | 未判定 |')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def audit_task(task):
    path, meta = task
    c = load_chart(path, meta)
    findings = lint(c)
    counts = Counter(f.level for f in findings)
    rules, categories = defaultdict(Counter), defaultdict(Counter)
    for f in findings:
        rules[f.rule][f.level] += 1
        if f.rule.startswith(('hand-', 'fast-jack')):
            categories[f.message.split(': ', 1)[0]][f.level] += 1
    return meta['group'], dict(counts), dict(rules), dict(categories)


def audit(tasks, policy, workers):
    counts = defaultdict(Counter)
    rules, categories = defaultdict(lambda: defaultdict(Counter)), defaultdict(lambda: defaultdict(Counter))
    with ProcessPoolExecutor(workers) as pool:
        for g, c, r, cats in pool.map(audit_task, tasks, chunksize=8):
            counts[g].update(c)
            for key, values in r.items():
                rules[g][key].update(values)
            for key, values in cats.items():
                categories[g][key].update(values)
    def rates(g, values):
        return {s: values[s] * 100 / max(policy['groups'][g]['measures'], 1) for s in ('warning', 'info')}
    return {g: {'counts': dict(counts[g]), 'rules': dict(rules[g]),
                'per_100_measures': rates(g, counts[g]),
                'categories': {k: {'counts': dict(v), 'per_100_measures': rates(g, v)}
                               for k, v in sorted(categories[g].items())}} for g in GROUPS}


def doc_intro(policy, rates):
    lines = ['## lint に反映した規則', '',
             '- 開始＋保持のボタン最小手数を span-3 の窓 A–C / B–D と、その下の FX '
             '（FX-L は A/B、FX-R は C/D）で計算する。開始／保持・正確なレーン集合はキーに入れない。'
             'キーは強い側を左にしたつまみ需要・ボタン手数・crossing。crossing は需要の軽い側の手で押すために自側の窓を越える場合。'
             'このモデルは全6ボタンを2手で覆え、A+D+両FXも2手（3手以上にする追加制約は未指定）。',
             '- 実効手数＝ボタン手数＋slam/steep 各1＋gentle/ending 各0.5。2以下は頻度検査をしない。'
             '2超で全公式群（KSM含む）未観測なら `hand-impossible` warning、対象群で0.05/100小節未満なら `hand-rare` info。',
             '- レーザーの phase 2 定義を維持: slam は前30〜後31 pulse未満、ending は連続移動終点まで50 ms以内、'
             'steep は32通常幅/秒超、その他の移動はgentle、静止・無しはstill。slam→ending→steepの順に優先。'
             '速度は局所BPM・幅・曲線の微分を使い、傾斜途中の点は移動終点にしない。',
             '- `fast-jack`（両手）／`fast-jack-one-hand`（片手・mixed・assisted）: 群・BT/FX別の従来p1未満をinfo。'
             '同群の5譜面以上で観測された最短帯の下端未満だけwarning。'
             '帯は <60 / 60–70 / 70–80 / 80–90 / 90–100 / 100–120 / 120 ms以上。'
             'assistedは反対手の占有がgentle/endingのみ、mixedは片手分布へ合算。',
             '- `placement_verdicts.json` のカテゴリ／ジャック行キーに人手判断があれば優先する。'
             '`allow` は抑制、`forbid` は `placement-forbidden` warning、`{"min_level": x}` はx未満で '
             '`placement-min-level` warning、x以上なら抑制。初期値は空。',
             '- 群: 17〜17.4→17、17.5〜18.9→18、19以上→19-20、17未満→ksm。別群へのフォールバックはしない。'
             '欠測のジャック閾値は判定しない。',
             '- `short-long` warning（1/8拍未満）と音源指定時の after-audio / unaligned / empty-loud / thin は維持。', '',
             f'全{len(policy["categories"])}カテゴリ、実効手数>2は'
             f'{sum(effective_hands(k) > 2 for k in policy["categories"])}カテゴリ。'
             '集計値のみのパッケージ表は `src/ksmauto/data/hand_categories.json`。'
             '群別の件数・譜面数・頻度と各群最大3例、およびジャックp1は [placement-review.md](placement-review.md)。', '',
             '### コーパスでの実行結果', '',
             '学習と同じコーパスへの再適用。SDVXの小数レベルはソースからメモリ上で復元する。'
             'KSMは集計上別群だがCLIは入力のmeta.levelで群を選ぶため、KSMのLv17以上では学習群と検査群が異なる。'
             '目標はwarning 0、info <1/100小節。手数規則と全lintを分けて示す。', '',
             '| 群 | 手数 warning /100小節 | 手数 info /100小節 | 全 warning /100小節 | 全 info /100小節 |',
             '|---|---:|---:|---:|---:|']
    for g, r in rates.items():
        hand = Counter()
        for rule, counts in r['rules'].items():
            if rule.startswith('hand-'):
                hand.update(counts)
        div = max(policy['groups'][g]['measures'], 1) / 100
        lines.append(f'| {g} | {hand["warning"] / div:.5f} | {hand["info"] / div:.5f} | '
                     f'{r["per_100_measures"]["warning"]:.5f} | {r["per_100_measures"]["info"]:.5f} |')
    lines += ['', '目標未達の内訳（件数ではなく100小節あたり。頻度境界は目標に合わせて変更しない）:', '',
              '| 群 | カテゴリ／既存規則 | warning /100小節 | info /100小節 |', '|---|---|---:|---:|']
    for g, r in rates.items():
        if not r['counts'].get('warning') and r['per_100_measures']['info'] < 1:
            continue
        for key, c in r['categories'].items():
            v = c['per_100_measures']
            lines.append(f'| {g} | {key.replace("|", "&#124;")} | {v["warning"]:.5f} | {v["info"]:.5f} |')
        for rule, c in r['rules'].items():
            if not rule.startswith(('hand-', 'fast-jack')):
                div = max(policy['groups'][g]['measures'], 1) / 100
                lines.append(f'| {g} | {rule} | {c.get("warning", 0) / div:.5f} | {c.get("info", 0) / div:.5f} |')
    return [*lines, '']
