from pathlib import Path

import pytest

from ksmauto.ksh import load_ksh
from ksmauto.lint import hand_policy, jack_intervals, jack_band, effective_hands
from ksmauto.timing import TimingMap
from eval.hand_policy import chart_evidence, build_policy, review_rows, write_review
from eval.placement_rules import aggregate, quantiles, tally, verdict


FIXTURES = Path(__file__).parent / 'fixtures' / 'libkson'


def chart(bt=None, fx=None, laser=None, bpm=120):
    return {'beat': {'bpm': [[0, bpm]]},
            'note': {'bt': bt or [[], [], [], []], 'fx': fx or [[], []],
                     'laser': laser or [[], []]}}


def rules(c):
    return tally(c)['rules']


@pytest.mark.parametrize('path', sorted(FIXTURES.glob('*.ksh')), ids=lambda p: p.name)
def test_fixture_tally_matches_lint(path):
    c = load_ksh(path)
    t = tally(c)
    assert t['measures'] > 0
    evidence = chart_evidence(c, hand_policy()['thresholds'])
    assert sum(evidence['categories'].values()) == len({y for lane in c['note']['bt'] + c['note']['fx']
                                                          for y, _ in ((n, 0) if isinstance(n, int) else n for n in lane)})
    intervals = list(jack_intervals(c, TimingMap(c['beat']), hand_policy()['thresholds']))
    for cls in ('one-hand', 'two-hand', 'assisted', 'mixed'):
        assert t['rules']['jack-' + cls]['count'] == sum(i[-1] == cls for i in intervals)
    assert t['button_starts'] == sum(len(lane) for kind in ('bt', 'fx') for lane in c['note'][kind])
    assert all(len(r['examples']) <= 5 for r in t['rules'].values())


def test_jack_hand_occupancy_and_long_end():
    r = rules(chart(bt=[[60, 90], [], [], []]))
    assert r['jack-two-hand']['count'] == 1
    assert r['jack-two-hand']['metrics']['BT_interval_ms'] == [62.5]
    assert r['jack-one-hand']['count'] == 0
    # A right long occupies the whole interval, while its endpoint is free.
    r = rules(chart(bt=[[60, 90, 120], [], [], [[0, 90]]]))
    assert r['jack-one-hand']['count'] == 1
    assert r['jack-two-hand']['count'] == 1
    # A right chip between the two A chips prevents a completely free interval.
    r = rules(chart(bt=[[60, 90], [], [], [75]]))
    assert r['jack-mixed']['count'] == 1
    assert r['jack-one-hand']['count'] == r['jack-two-hand']['count'] == 0
    r = rules(chart(bt=[[[0, 60], 90], [], [], []]))
    assert r['jack-two-hand']['by']['BT:long-end'] == 1
    assert r['long-end-to-chip']['metrics']['interval_ms'] == [62.5]
    # A's home knob forces the right hand to repeat A, with gentle assist.
    r = rules(chart(bt=[[60, 90], [], [], []], laser=[[[0, [[0, 0], [120, 1]]]], []]))
    assert r['jack-assisted']['count'] == 1
    # Partial knob occupancy is a third category, not full-interval occupancy.
    r = rules(chart(bt=[[0, 120], [], [], []], laser=[[], [[60, [[0, 0], [60, 1]]]]]))
    assert r['jack-assisted']['count'] == 1


def test_trill_runs_and_breaks():
    c = chart(bt=[[60, 120, 180], [90, 150], [], [[0, 240]]])
    r = rules(c)
    assert r['trill-one-hand']['count'] == 1
    assert r['trill-one-hand']['metrics']['run_hits'] == [5]
    assert r['trill-one-hand']['metrics']['hit_interval_ms'] == [62.5] * 4
    c['note']['bt'][1].append(180)  # chord breaks the last hit
    assert rules(c)['trill-one-hand']['metrics']['run_hits'] == [4]
    # A BC run with both FX held has two possible assignments, one occurrence.
    c = chart(bt=[[], [60, 120], [90, 150], []], fx=[[[0, 240]], [[0, 240]]])
    assert rules(c)['trill-one-hand']['metrics']['run_hits'] == [4]
    # BC is reachable by the right hand while the left knob turns.
    c = chart(bt=[[], [60, 120], [90, 150], []], laser=[[[0, [[0, 0], [240, 1]]]], []])
    assert rules(c)['trill-one-hand']['metrics']['run_hits'] == [4]


def test_crossing_exact_intersection_and_wide():
    c = chart(bt=[[60, 120, 180, 240], [], [], []],
              laser=[[[0, [[0, 0], [240, 1]]]], [[0, [[0, 0.5], [240, 0.5]]]]])
    r = rules(c)['laser-crossing']
    assert r['count'] == 1
    assert r['metrics']['duration_ms'] == [250]
    assert r['by']['button_start_times'] == 2  # equality at 120 is not crossing
    c['note']['laser'][0][0].append(2)
    c['note']['laser'][1][0][1] = [[0, 0.75], [240, 0.75]]
    r = rules(c)
    assert r['wide-laser']['count'] == 1
    assert r['laser-crossing']['metrics']['duration_ms'] == [187.5]
    # A standalone slam can cross at a single instant.
    c = chart(laser=[[[120, [[0, [0, 1]]]]], [[0, [[0, 0.5], [240, 0.5]]]]])
    assert rules(c)['laser-crossing']['metrics']['duration_ms'] == [0]


def test_curved_laser_crossing():
    # Quadratic control (0.5,0): at half the pulse span, value is 0.25.
    c = chart(bt=[[120, 180], [], [], []],
              laser=[[[0, [[0, 0, [0.5, 0]], [240, 1]]]],
                     [[0, [[0, 0.25], [240, 0.25]]]]])
    t = tally(c)
    assert t['curve_points'] == 1
    assert t['rules']['laser-crossing']['metrics']['duration_ms'] == [250]
    assert t['rules']['laser-crossing']['by']['button_start_times'] == 1


def test_slams_direction_interval_and_delay():
    points = [[0, [0, 1]], [30, 1], [120, [1, 0]], [150, 0]]
    c = chart(bt=[[0, 10, 15, 16, 120], [], [], []], laser=[[[0, points]], []])
    r = rules(c)
    assert r['slam-interval']['metrics']['interval_ms'] == [250]
    assert r['slam-interval']['by']['near_section_start'] == 1
    assert r['slam-with-button']['by'] == {'L:left:A': 1, 'L:right:A': 1}
    assert r['button-during-slam-same-hand']['count'] == 2
    assert r['button-during-slam-same-hand']['metrics']['delay_ms'] == [20.833333, 31.25]
    # Mirroring the chart preserves the normalised slam direction and shape.
    c = chart(bt=[[], [], [], [0, 120]],
              laser=[[], [[0, [[0, [1, 0]], [30, 0], [120, [0, 1]], [150, 1]]]]])
    assert rules(c)['slam-with-button']['by'] == {'L:left:A': 1, 'L:right:A': 1}


def test_hold_chips_grids_and_short_longs():
    c = chart(bt=[[[0, 120]], [20, 30, 40, 60, 80, 120], [], [30]],
              fx=[[[0, 120]], []], laser=[[], [[0, [[0, 0], [120, 1]]]]])
    r = rules(c)
    assert r['fx-long-with-bt-chips']['count'] == 5  # endpoint excluded
    assert r['hold-and-chip']['by']['reach:hold-A+chip-B'] == 5
    assert r['hold-and-chip']['by']['leave:hold-A+chip-D'] == 1
    # The target D chip is not itself evidence that the right hand is busy.
    free = rules(chart(bt=[[[0, 120]], [], [], [60]]))
    assert free['hold-and-chip']['count'] == 0
    assert r['offgrid']['by'] == {'1/24': 1, '1/32': 2, '1/48': 1}
    c = chart(bt=[[[0, 29], [60, 30], [120, 60]], [], [], []])
    r = rules(c)['short-long']
    assert r['count'] == 1
    assert r['metrics']['all_long_beats'] == [29 / 240, 0.125, 0.25]


def test_laser_gap_and_reversals():
    c = chart(laser=[[[0, [[0, 0], [60, 1], [120, 0], [180, 1], [240, 0]]],
                      [270, [[0, 1], [330, 0]]]], []])
    r = rules(c)
    assert r['laser-zigzag']['count'] == 3
    assert r['laser-zigzag']['metrics']['reversal_interval_ms'] == [125, 125]
    assert r['laser-gap']['metrics']['gap_ms'] == [62.5]


def test_density_chords_and_timing_changes():
    c = chart(bt=[[0, 120, 240, 360, 480], [0], [], []])
    r = rules(c)
    assert r['stream-density']['metrics']['peak_1s_nps'] == [4]
    assert r['stream-density']['metrics']['peak_4s_nps'] == [1.25]
    assert r['chord-shapes']['by']['free:A+B'] == 1
    c = chart(bt=[[0, 240], [], [], []])
    c['beat']['bpm'].append([120, 240])
    assert rules(c)['jack-two-hand']['metrics']['BT_interval_ms'] == [375]
    c['beat']['time_sig'] = [[0, [3, 4]], [1, [4, 4]]]
    c['note']['bt'][0] = [0, 720, 1680]
    assert tally(c)['measures'] == 3
    assert rules(c)['jack-two-hand']['examples'][-1]['measure'] == 2


def test_shapes_and_knob_occupancy():
    c = chart(bt=[[60], [60], [60], [60]], fx=[[60], [60]])
    r = rules(c)['chord-shapes']
    assert r['count'] == 1
    assert r['by']['free:A+B+C+D+FL+FR'] == 1
    assert r['by']['free:flag:3plus-BT'] == r['by']['free:flag:4-BT'] == 1
    assert r['by']['free:flag:FX+two-home-BT'] == 1
    slope = [[0, [[0, 0], [240, 1]]]]
    c['note']['laser'] = [slope, slope]
    r = rules(c)
    assert r['both-knobs-and-button']['count'] == 1
    assert r['both-knobs-and-button']['by']['lane:FL'] == 1
    assert r['hand-overload']['count'] == 1
    assert r['chord-shapes']['count'] == r['knob-crossing-press']['count'] == 0
    c = chart(bt=[[], [], [], [60]], fx=[[], [60]], laser=[[], slope])
    assert rules(c)['knob-crossing-press']['by'] == {'A': 1, 'FL': 1}


def test_group_aggregation_verdict_and_quantiles():
    rows = [{'meta': {'group': 'ksm', 'key': 'tiny', 'title': 'Tiny', 'level': 1, 'file': 'tiny.ksh'},
             'tally': tally(chart(bt=[[0, 60], [], [], []]))}]
    report = aggregate(rows)
    assert report['rules']['jack-two-hand']['ksm']['occurrences'] == 1
    assert report['rules']['jack-two-hand']['ksm']['per_100_measures'] == 100
    assert report['rules']['jack-two-hand']['ksm']['examples'][0]['file'] == 'tiny.ksh'
    assert report['rules']['both-knobs-and-button']['ksm']['verdict'] == 'never'
    assert report['rules']['jack-two-hand']['17']['verdict'] == 'rare'
    assert verdict(1, 1, 1000, 100, True) == 'rare'
    assert verdict(1, 1, 100, 20, True) == 'common'
    assert quantiles([0, 100])['p1'] == 1


def test_decode_noise_filter_retains_real_fast_slams():
    c = chart(laser=[[[0, [[0, 0], [60, 1], [65, .98], [120, 0], [180, 1]]]], []])
    r = rules(c)['laser-zigzag']
    assert r['by']['decode_short_reversal_excluded'] == 1
    assert r['count'] == 1
    c = chart(laser=[[[0, [[0, [0, .5]], [20, [0, .5]], [40, [.5, 0]]]]], []])
    r = rules(c)['slam-interval']
    assert r['by']['decode_short_interval_excluded'] == 1
    assert r['count'] == 1  # rapid opposite-direction slam is retained


def test_policy_aggregates_review_and_percentiles():
    c = chart(bt=[[0, 30, 60], [], [], [15]])
    row = {'meta': {'group': '18', 'title': 'Tiny'}, 'tally': tally(c),
           'hand': chart_evidence(c, hand_policy()['thresholds'])}
    policy = build_policy([row], hand_policy()['thresholds'])
    assert policy['groups']['18'] == {'charts': 1, 'measures': 1}
    assert policy['jacks']['18']['one-hand']['BT']['count'] == 1
    assert policy['jacks']['18']['one-hand']['BT']['p1_ms'] == 62.5
    assert policy['jacks']['17']['one-hand']['BT']['p1_ms'] is None
    assert all(v['18']['charts'] == 1 for v in policy['categories'].values())
    policy['groups']['18']['measures'] = 10000
    review = review_rows([row], policy)
    assert review == []  # no overloaded categories in this chart


@pytest.mark.parametrize('dt,index', [(0, 0), (59.999, 0), (60, 1), (70, 2), (80, 3),
                                     (90, 4), (100, 5), (119.999, 5), (120, 6), (2000, 6)])
def test_jack_bands(dt, index):
    assert jack_band(dt) == index


def test_robust_minimum_counts_charts_not_repeats():
    def row(dts):
        return {'meta': {'group': '17', 'title': 'Test'}, 'tally': {'measures': 100},
                'hand': {'categories': {}, 'examples': {},
                         'jacks': [['two-hand', 'BT', dt, 0] for dt in dts]}}
    rows = [row([10] * 100 + [65, 75]), *[row([65, 75]) for _ in range(3)]]
    policy = build_policy(rows, hand_policy()['thresholds'])
    r = policy['jacks']['17']['two-hand']['BT']
    assert r['robust_min_ms'] is None
    assert r['bands'][0]['charts'] == 1
    rows.append(row([75]))
    r = build_policy(rows, hand_policy()['thresholds'])['jacks']['17']['two-hand']['BT']
    assert r['robust_min_ms'] == 70
    assert [b['charts'] for b in r['bands'][:3]] == [1, 4, 5]
    assert sum(b['count'] for b in r['bands']) == r['count']


def test_review_lists_all_overloaded_categories_and_24_jack_rows(tmp_path):
    c = chart(bt=[[120], [], [], []], laser=[[[120, [[0, [0, 1]]]]]] * 2)
    row = {'meta': {'group': '18', 'title': 'Tiny'}, 'tally': tally(c),
           'hand': chart_evidence(c, hand_policy()['thresholds'])}
    policy = build_policy([row], hand_policy()['thresholds'])
    review = review_rows([row], policy)
    assert len(review) == 1
    assert effective_hands(review[0][0]) == 3
    assert dict(review[0][-1]) == {'18': [('Tiny', 0)]}
    path = tmp_path / 'review.md'
    write_review([row], policy, path)
    assert path.read_text().count('| 未判定 |') == 25
