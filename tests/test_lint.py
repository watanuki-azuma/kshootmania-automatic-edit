from pathlib import Path
from copy import deepcopy

import pytest

from ksmauto.ksh import load_ksh
from ksmauto.lint import (_hands_for_buttons, lint, stats, hand_policy, level_group,
                          laser_demands, demand_at, slope_at, category_key, effective_hands,
                          button_categories, jack_intervals, jack_key, MIRROR_LANES)
from ksmauto.timing import TimingMap

GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"



@pytest.fixture(autouse=True)
def no_verdicts(monkeypatch):
    # Tests that need verdicts set their own; the shipped ones must not leak in.
    monkeypatch.setattr('ksmauto.lint.placement_verdicts', lambda: {})

def _chart(bt=None, fx=None, laser=None, bpm=120.0):
    return {
        "format_version": 1,
        "meta": {"title": "t", "artist": "", "chart_author": "", "difficulty": 0, "level": 1, "disp_bpm": "120"},
        "beat": {"bpm": [[0, bpm]]},
        "note": {"bt": bt or [[], [], [], []], "fx": fx or [[], []], "laser": laser or [[], []]},
    }


def test_hands_for_buttons():
    assert _hands_for_buttons([("bt", 1), ("bt", 2)]) == 1
    assert _hands_for_buttons([("fx", 0), ("fx", 1)]) == 2
    assert _hands_for_buttons([("bt", 0), ("bt", 3)]) == 2
    assert _hands_for_buttons([("bt", 0), ("fx", 1)]) == 2


def test_fast_jack():
    c = _chart(bt=[[0, 30], [], [], []], bpm=120.0)  # 30 pulses = 62.5 ms at 120 BPM
    assert [f.rule for f in lint(c)] == ["fast-jack"]


def test_assist_combinations_are_observed():
    moving = [[0, [[0, 0.0], [960, 1.0]]]]
    still = [[0, [[0, 0.5], [960, 0.5]]]]
    c = _chart(bt=[[240], [], [], [240]], laser=[moving, []])
    assert not any(f.level == 'warning' for f in lint(c))
    c['note']['laser'] = [still, []]
    assert lint(c) == []


@pytest.mark.parametrize('level,group', [(1, 'ksm'), (16.9, 'ksm'), (17, '17'),
                                       (17.4, '17'), (17.5, '18'), (18.9, '18'), (19, '19-20'), (20.9, '19-20')])
def test_level_groups(level, group):
    assert level_group(level) == group


def test_lookup_group_rarity_and_impossibility(monkeypatch):
    policy = deepcopy(hand_policy())
    slam = [[120, [[0, [0, 1]]]]]
    c = _chart(bt=[[120], [], [], []], laser=[slam, slam])
    c['meta']['level'] = 17
    key = next(button_categories(c, TimingMap(c['beat']), policy['thresholds']))[1]
    policy['categories'] = {key: {g: {'count': 0, 'charts': 0, 'per_100_measures': 0}
                                   for g in policy['groups']}}
    policy['categories'][key]['17'] = {'count': 3, 'charts': 3, 'per_100_measures': .01}
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    rare = lint(c)
    assert len(rare) == 1 and rare[0].rule == 'hand-rare' and rare[0].level == 'info'
    assert 'official Lv17: 0.01/100 measures, 3 charts' in rare[0].message
    policy['categories'][key]['17']['per_100_measures'] = .05
    assert lint(c) == []  # strict rarity boundary
    c['meta']['level'] = 17.5
    assert 'official Lv18: 0.00/100 measures, 0 charts' in lint(c)[0].message
    c['meta']['level'] = 1
    assert 'official Lvksm: 0.00/100 measures, 0 charts' in lint(c)[0].message
    policy['categories'].clear()
    assert [(f.level, f.rule) for f in lint(c)] == [('warning', 'hand-impossible')]
    assert lint(_chart(bt=[[120], [], [], []])) == []  # <=2 never needs corpus support


def test_demand_classes_endpoints_slam_width_and_tempo():
    th = {'ending_sec': .05, 'steep_widths_per_sec': 1.5}
    c = _chart(laser=[[[0, [[0, 0], [240, 1], [480, 1]]]], []])
    t = TimingMap(c['beat']); p = laser_demands(c, t)[0]
    assert demand_at(p, t, 0, th) == 'steep'  # two widths/second
    assert demand_at(p, t, 216, th) == 'ending'
    assert demand_at(p, t, 240, th) == demand_at(p, t, 600, th) == 'still'
    c['beat']['bpm'] = [[0, 60], [120, 120]]
    t = TimingMap(c['beat']); p = laser_demands(c, t)[0]
    assert demand_at(p, t, 60, th) == 'gentle'
    assert demand_at(p, t, 120, th) == 'steep'
    c['note']['laser'][0][0].append(2)
    assert slope_at(laser_demands(c, t)[0], t, 60)[0] == 2
    c['note']['laser'][0] = [[120, [[0, [0, 1]]]]]
    p = laser_demands(c, t)[0]
    assert demand_at(p, t, 89, th) == 'still'
    assert all(demand_at(p, t, y, th) == 'slam' for y in (90, 120, 150))
    assert demand_at(p, t, 151, th) == 'still'


def test_curve_speed_and_movement_endpoint():
    c = _chart(laser=[[[0, [[0, 0, [.5, 0]], [120, .25], [240, 1], [480, 1]]]], []])
    t = TimingMap(c['beat']); p = laser_demands(c, t)[0]
    assert slope_at(p, t, 60) == (1, .375)
    # The intermediate point is not a movement endpoint.
    assert demand_at(p, t, 110, {'ending_sec': .05, 'steep_widths_per_sec': 32}) == 'gentle'


@pytest.mark.parametrize('lanes,hands', [([], 0), ([0, 1, 2], 1), ([1, 2, 3], 1),
                                             ([0, 3], 2), ([0, 4], 1), ([2, 4], 1),
                                             ([1, 5], 1), ([3, 4], 2), ([0, 5], 2),
                                             ([4, 5], 2), ([0, 3, 4, 5], 2),
                                             (list(range(6)), 2)])
def test_span_three_and_fx_footprints(lanes, hands):
    pressed = [('bt', l) if l < 4 else ('fx', l - 4) for l in lanes]
    assert _hands_for_buttons(pressed) == hands


def test_category_mirroring_and_crossing():
    for mask in range(64):
        lanes = [l for l in range(6) if mask & (1 << l)]
        assert category_key(['still', 'steep'], lanes) == category_key(
            ['steep', 'still'], [MIRROR_LANES[l] for l in lanes])
        assert category_key(['slam', 'slam'], lanes) == category_key(
            ['slam', 'slam'], [MIRROR_LANES[l] for l in lanes])
    assert category_key(['steep', 'still'], [0, 4]) == 'steep,still|1|crossing'
    assert category_key(['steep', 'still'], [1, 2, 3, 5]) == 'steep,still|1|home'
    assert category_key(['steep', 'still'], [0, 3]) == 'steep,still|2|home'
    assert category_key(['still', 'still'], [1]) == category_key(['still', 'still'], [0, 1, 2, 4])


def test_category_held_endpoints():
    c = _chart(bt=[[[0, 120]], [], [], [60, 120]])
    rows = list(button_categories(c, TimingMap(c['beat']), hand_policy()['thresholds']))
    assert [effective_hands(r[1]) for r in rows] == [1, 2, 1]
    assert rows[1][3] == [(3, 'S'), (0, 'H')]
    assert rows[2][3] == [(3, 'S')]
    assert rows[0][1] == rows[2][1]


@pytest.mark.parametrize('demands,lanes,expected', [(['still', 'still'], [], 0),
    (['steep', 'still'], [0], 2), (['gentle', 'ending'], [1, 2], 2),
    (['gentle', 'still'], [0, 3], 2.5), (['slam', 'gentle'], [0], 2.5),
    (['slam', 'steep'], [0, 3], 4)])
def test_effective_hands(demands, lanes, expected):
    assert effective_hands(category_key(demands, lanes)) == expected


@pytest.mark.parametrize('verdict,level,rule', [('allow', 17, None), ('forbid', 18, 'placement-forbidden'),
    ({'min_level': 18}, 17.4, 'placement-min-level'), ({'min_level': 18}, 17.5, None),
    ({'min_level': 19}, 18.9, 'placement-min-level'), ({'min_level': 19}, 19, None)])
@pytest.mark.parametrize('overload', [False, True])
def test_category_verdict_overrides_frequency_and_safe_hand_count(monkeypatch, verdict, level, rule, overload):
    policy = deepcopy(hand_policy())
    policy['categories'] = {}
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    slam = [[120, [[0, [0, 1]]]]]
    c = _chart(bt=[[120], [], [], []], laser=[slam, slam] if overload else None)
    c['meta']['level'] = level
    key = next(button_categories(c, TimingMap(c['beat']), policy['thresholds']))[1]
    monkeypatch.setattr('ksmauto.lint.placement_verdicts', lambda: {key: verdict})
    assert [(f.level, f.rule) for f in lint(c)] == ([] if rule is None else [('warning', rule)])


@pytest.mark.parametrize('occupancy,expected', [('free', 'two-hand'), ('hold', 'one-hand'),
                                              ('chip', 'mixed'), ('gentle', 'assisted'),
                                              ('steep', 'one-hand'), ('ending', 'assisted'), ('slam', 'one-hand')])
def test_shared_jack_classification(occupancy, expected):
    c = _chart(bt=[[60, 90], [], [], []])
    th = {'ending_sec': .05, 'steep_widths_per_sec': 1.5}
    if occupancy == 'hold':
        c['note']['bt'][3] = [[0, 120]]
    elif occupancy == 'chip':
        c['note']['bt'][3] = [75]
    elif occupancy in ('gentle', 'steep', 'ending'):
        c['note']['laser'][1] = [[0, [[0, 0], [100 if occupancy == 'ending' else 240, .1 if occupancy == 'gentle' else 1]]]]
        if occupancy == 'ending':
            c['note']['bt'][0] = [80, 90]
    elif occupancy == 'slam':
        c['note']['laser'][1] = [[75, [[0, [0, 1]]]]]
    assert list(jack_intervals(c, TimingMap(c['beat']), th))[0][-1] == expected


@pytest.mark.parametrize('kind', ['BT', 'FX'])
def test_jack_uses_group_p1_and_mixed_one_hand(monkeypatch, kind):
    policy = deepcopy(hand_policy())
    policy['jacks']['18']['two-hand'][kind].update(p1_ms=50, robust_min_ms=None)
    policy['jacks']['18']['one-hand'][kind].update(p1_ms=70, robust_min_ms=None)
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    c = _chart(bt=[[60, 90], [], [], []] if kind == 'BT' else None,
               fx=[[60, 90], []] if kind == 'FX' else None)
    c['meta']['level'] = 17.5
    assert not any(f.rule.startswith('fast-jack') for f in lint(c))
    c['note']['bt'][3] = [75]  # mixed, counted against one-hand p1
    f = next(f for f in lint(c) if f.rule.startswith('fast-jack'))
    assert f.rule == 'fast-jack-one-hand' and f.level == 'info'
    assert 'info below 70 ms, warning below off' in f.message


@pytest.mark.parametrize('verdict,expected', [({'warn_ms': 1000, 'info_ms': None}, [('warning', 'fast-jack')]),
                                              ({'warn_ms': None, 'info_ms': 1000}, [('info', 'fast-jack')]),
                                              ({'warn_ms': None, 'info_ms': None}, [])])
def test_jack_verdict_replaces_thresholds(monkeypatch, verdict, expected):
    policy = deepcopy(hand_policy())
    policy['jacks']['18']['two-hand']['BT'].update(p1_ms=1000, robust_min_ms=None)
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    monkeypatch.setattr('ksmauto.lint.placement_verdicts', lambda: {'jack:18:two-hand:BT': verdict})
    c = _chart(bt=[[60, 90], [], [], []])
    c['meta']['level'] = 18
    assert [(f.level, f.rule) for f in lint(c) if f.rule.startswith('fast-jack')] == expected


def _analysis(measures):
    return {"audio": {"duration_sec": 30}, "tempo": {"time_sig": [4, 4]}, "measures": measures}


def test_thin_vocal_with_laser():
    vocal = [[b / 2, 0.3] for b in range(7)]
    analysis = _analysis([{"index": 0, "energy": 0.8, "onsets": {"all": vocal},
                           "stems": {"onsets": {"vocal": vocal}}}])
    c = _chart(bt=[[[0, 240]], [], [], []], fx=[[480], []],
               laser=[[[0, [[0, 0.0], [960, 1.0]]]], []])
    findings = lint(c, analysis)
    thin = [f for f in findings if f.rule == "thin"]
    assert len(thin) == 1
    assert (thin[0].level, thin[0].where) == ("info", "m0")
    assert thin[0].message == "vocal sings 7 notes, 2 button notes: follow its rhythm or make the rest deliberate"
    assert not any(f.rule == "empty-loud" for f in findings)
    c["note"]["bt"] = [[], [], [], []]
    c["note"]["fx"] = [[], []]
    findings = lint(c, analysis)
    assert any(f.rule == "thin" and "0 button notes" in f.message for f in findings)
    assert not any(f.rule == "empty-loud" for f in findings)


def test_thin_thresholds():
    analysis = _analysis([
        {"index": i, "energy": 0.1, "onsets": {},
         "stems": {"onsets": {"vocal": [[b, s] for b, s in enumerate(strengths)]}}}
        for i, strengths in enumerate(([0.3, 0.6, 1.0, 0.299], [0.3] * 4, [0.3] * 4))
    ])
    c = _chart(bt=[[960, 1200, 1440, 1920], [[1920, 240]], [], []],
               fx=[[1920], [[1920, 480]]])
    thin = [f for f in lint(c, analysis) if f.rule == "thin"]
    assert len(thin) == 1
    assert thin[0].where == "m1"
    assert thin[0].message == "vocal sings 4 notes, 3 button notes: follow its rhythm or make the rest deliberate"


def test_thin_requires_vocal_stems():
    vocal = [[b, 1.0] for b in range(4)]
    analysis = _analysis([
        {"index": 0, "energy": 0.8, "onsets": {"mid": vocal}},
        {"index": 1, "energy": 0.8, "onsets": {}, "stems": {"onsets": {"vocal": []}}},
        {"index": 2, "energy": 0.8, "onsets": {}, "stems": {"onsets": {"other": vocal}}},
    ])
    findings = lint(_chart(), analysis)
    assert not any(f.rule == "thin" for f in findings)
    assert [f.where for f in findings if f.rule == "empty-loud"] == ["m0", "m1", "m2"]


def test_thin_counts_only_starts_in_measure():
    c = _chart(bt=[[[0, 1440]], [720], [1440, 1680], [1440]])
    c["beat"]["time_sig"] = [[0, [3, 4]]]
    vocal = [[b / 2, 0.6] for b in range(4)]
    analysis = _analysis([{"index": 1, "energy": 0.1, "onsets": {"mid": vocal},
                           "stems": {"onsets": {"vocal": vocal}}}])
    analysis["tempo"]["time_sig"] = [3, 4]
    thin = [f for f in lint(c, analysis) if f.rule == "thin"]
    assert len(thin) == 1
    assert thin[0].where == "m1"
    assert thin[0].message == "vocal sings 4 notes, 1 button notes: follow its rhythm or make the rest deliberate"


def test_stats_on_gram():
    s = stats(load_ksh(GRAM))
    assert s["bt_chips"] > 100 and s["slams"] > 0
    assert 10 <= s["level_estimate"] <= 20


def test_chain_ticks_follow_ksm_v2():
    from ksmauto.lint import chain_ticks

    def chart(bt=(), laser=(), bpm=180.0):
        return {"beat": {"bpm": [[0, bpm]]}, "note": {"bt": [list(bt), [], [], []], "fx": [[], []], "laser": [list(laser), []]}}

    assert len(chain_ticks(chart(bt=[0, [960, 60], [1920, 180]]))) == 3     # chip, short holds count once
    assert chain_ticks(chart(bt=[[0, 960]]))[:2] == [60, 120] and len(chain_ticks(chart(bt=[[0, 960]]))) == 14
    assert len(chain_ticks(chart(bt=[[0, 960]], bpm=256.0))) == 6          # 8th ticks from BPM 256
    assert chain_ticks(chart(laser=[[0, [[0, 0.0], [240, 1.0]]]])) == [0, 60, 120, 180]
    assert chain_ticks(chart(laser=[[0, [[0, [0.0, 1.0]]]]])) == [0]          # lone slam
    assert chain_ticks(chart(laser=[[0, [[0, [0.0, 1.0]], [240, 0.5]]]])) == [0, 60, 120, 180]
    assert chain_ticks(chart(laser=[[0, [[0, [0.0, 1.0]], [30, 1.0], [270, 0.0]]]])) == [0, 60, 120, 180, 240]


def test_packaged_policy_is_aggregate_only():
    policy = hand_policy()
    assert set(policy['groups']) == {'17', '18', '19-20', 'ksm'}
    assert policy['categories']
    for groups in policy['categories'].values():
        assert any(row['count'] > 0 for row in groups.values())
        for row in groups.values():
            assert set(row) == {'count', 'charts', 'per_100_measures'}
            assert 0 <= row['charts'] <= row['count']
    assert all(set(row) == {'charts', 'measures'} for row in policy['groups'].values())


def test_jack_threshold_is_strict_at_p1(monkeypatch):
    policy = deepcopy(hand_policy())
    policy['jacks']['17']['two-hand']['BT'].update(p1_ms=62.5, robust_min_ms=None)
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    c = _chart(bt=[[0, 30], [], [], []])
    c['meta']['level'] = 17
    assert not any(f.rule == 'fast-jack' for f in lint(c))
    c['note']['bt'][0][1] = 29
    assert any(f.rule == 'fast-jack' for f in lint(c))


def test_curved_jack_interval_crosses_steep_boundary():
    c = _chart(bt=[[60, 90, 150, 180], [], [], []],
               laser=[[], [[0, [[0, 0, [.5, 0]], [240, 1]]]]])
    th = {'ending_sec': .05, 'steep_widths_per_sec': 2}
    assert [i[-1] for i in jack_intervals(c, TimingMap(c['beat']), th)] == ['assisted', 'one-hand', 'one-hand']


@pytest.mark.parametrize('pulses,severity', [(28, 'warning'), (29, 'info'), (30, 'info'), (39, None)])
def test_jack_robust_band_warning_and_p1_info(monkeypatch, pulses, severity):
    policy = deepcopy(hand_policy())
    policy['jacks']['17']['two-hand']['BT'].update(p1_ms=80, robust_min_ms=60)
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    c = _chart(bt=[[0, pulses], [], [], []])
    c['meta']['level'] = 17
    findings = [f for f in lint(c) if f.rule == 'fast-jack']
    assert [f.level for f in findings] == ([] if severity is None else [severity])


def test_jack_band_lower_edge_is_not_warning(monkeypatch):
    policy = deepcopy(hand_policy())
    policy['jacks']['17']['two-hand']['BT'].update(p1_ms=80, robust_min_ms=60)
    monkeypatch.setattr('ksmauto.lint.hand_policy', lambda: policy)
    c = _chart(bt=[[0, 30], [], [], []], bpm=125)  # exactly 60 ms
    c['meta']['level'] = 17
    assert [(f.rule, f.level) for f in lint(c)] == [('fast-jack', 'info')]


@pytest.mark.parametrize('verdict,level,rule', [('allow', 17, None), ('forbid', 17, 'placement-forbidden'),
    ({'min_level': 18}, 17.4, 'placement-min-level'), ({'min_level': 18}, 17.5, None),
    ({'min_level': 19}, 18.9, 'placement-min-level'), ({'min_level': 19}, 19, None)])
def test_jack_row_verdict(monkeypatch, verdict, level, rule):
    c = _chart(bt=[[0, 10], [], [], []])
    c['meta']['level'] = level
    key = jack_key(level_group(level), 'two-hand', 'BT')
    monkeypatch.setattr('ksmauto.lint.placement_verdicts', lambda: {key: verdict})
    assert [(f.level, f.rule) for f in lint(c)] == ([] if rule is None else [('warning', rule)])
