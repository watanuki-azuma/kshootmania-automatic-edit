import builtins
import json
from pathlib import Path

import pytest

from ksmauto.cli import main
from ksmauto.kson import load_kson, validate
from ksmauto.sdvxin import decode_report, load_sdvxin, report, sdvx_counts


@pytest.fixture
def json_chart(tmp_path):
    meta = {'kind': 'json', 'title': 'Inline', 'artist': 'Test', 'level': 18.4,
            'bpm': '180-300', 'counts': {'chip': '3', 'hold': '4', 'laser': '5'}}
    data = {'version': 'drawLasers.v1', 'notes': [
                {'type': 'BT', 'lane': 'D', 'pulse': 120},
                {'type': 'FX', 'lane': 'L', 'pulse': 0},
                {'type': 'BT', 'lane': 'A', 'pulse': 0}],
            'holds': [{'type': 'BT_HOLD', 'lane': 'B', 'pulse': 240, 'pulseEnd': 480}],
            'lasers': {'left': [[0, [[0, [0, 1], [0.4, 0.8]], [240, [1, 0]]], 2]],
                       'right': []},
            'bpm': [{'y': 960, 'v': 300}, {'y': 0, 'v': 180}, {'y': 960, 'v': 300}],
            'timeSig': [[0, [4, 4]], [1920, [3, 4]], [3360, [4, 4]]]}
    (tmp_path / 'meta.json').write_text(json.dumps(meta))
    (tmp_path / 'chart.json').write_text(json.dumps(data))
    return tmp_path


def test_json_conversion(json_chart):
    chart = load_sdvxin(json_chart)
    assert chart['meta'] == {'title': 'Inline', 'artist': 'Test', 'chart_author': 'sdvx.in transcription',
                             'difficulty': 3, 'level': 18.4, 'disp_bpm': '180-300',
                             'information': 'sdvx.in 18.4'}
    assert chart['beat'] == {'bpm': [[0, 180.0], [960, 300.0]],
                             'time_sig': [[0, [4, 4]], [2, [3, 4]], [4, [4, 4]]]}
    assert chart['note']['bt'] == [[[0, 0]], [[240, 240]], [], [[120, 0]]]
    assert chart['note']['fx'] == [[[0, 0]], []]
    assert chart['note']['laser'][0] == [[0, [[0, [0, 1], [0.4, 0.8]], [240, [1, 0]]], 2]]
    assert not validate(chart)


def test_json_bars_and_duplicate_laser_points(json_chart):
    path = json_chart / 'chart.json'
    data = json.loads(path.read_text())
    data['bars'] = [{'num': 6, 'den': 8, 'len': 720}, {'num': 6, 'den': 8, 'len': 720},
                    {'num': 4, 'den': 4, 'len': 960}]
    data['lasers']['right'] = [[480, [[0, 0.25], [0, 0.75], [120, 0.5, [0.5, 0.55]]], '2x']]
    path.write_text(json.dumps(data))
    chart = load_sdvxin(json_chart)
    assert chart['beat']['time_sig'] == [[0, [6, 8]], [2, [4, 4]]]
    assert chart['note']['laser'][1] == [[480, [[0, [0.25, 0.75]], [120, 0.5]], 2]]
    assert not validate(chart)


def test_json_needs_no_image_dependencies(json_chart, monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'numpy', 'PIL'}:
            raise ImportError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    assert load_sdvxin(json_chart)['meta']['title'] == 'Inline'


def test_counts_and_report_are_independent_of_official_counts(json_chart):
    chart = load_sdvxin(json_chart)
    assert sdvx_counts(chart) == {'chip': 3, 'hold': 4, 'laser': 5}
    before = decode_report(json_chart)
    meta_path = json_chart / 'meta.json'
    meta = json.loads(meta_path.read_text())
    meta['counts'] = dict.fromkeys(('chip', 'hold', 'laser'), '999')
    meta_path.write_text(json.dumps(meta))
    after = decode_report(json_chart)
    assert after['decoded'] == before['decoded']
    assert load_sdvxin(json_chart) == chart
    assert before['ok'] and not after['ok']


def test_count_bpm_threshold_and_changes(json_chart):
    chart = load_sdvxin(json_chart)
    chart['note'] = {'bt': [[[0, 480]], [], [], []], 'fx': [[], []], 'laser': [[], []]}
    chart['beat']['bpm'] = [[0, 254], [240, 255]]
    assert sdvx_counts(chart)['hold'] == 5
    chart['beat']['bpm'] = [[0, 255]]
    assert sdvx_counts(chart)['hold'] == 4
    chart['note']['laser'][0] = [[120, [[0, [0, 1]]], 2]]
    assert sdvx_counts(chart)['laser'] == 1


def test_json_rejects_unknown_format_and_mid_measure_signature(json_chart):
    path = json_chart / 'chart.json'
    data = json.loads(path.read_text())
    data['timeSig'].append([3500, [7, 8]])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='measure boundary'):
        load_sdvxin(json_chart)
    data['version'] = 'unknown'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unsupported'):
        load_sdvxin(json_chart)


def test_cli_json_and_report(json_chart, tmp_path, capsys):
    out = tmp_path / 'decoded.kson'
    assert main(['sdvxin', str(json_chart), '-o', str(out)]) == 0
    assert load_kson(out) == load_sdvxin(json_chart)
    assert main(['sdvxin', str(json_chart)]) == 0
    assert json.loads(capsys.readouterr().out)['meta']['title'] == 'Inline'
    root = tmp_path / 'corpus'
    target = root / '07' / 'inline'
    target.mkdir(parents=True)
    for name in ('meta.json', 'chart.json'):
        (target / name).write_text((json_chart / name).read_text())
    assert main(['sdvxin', '--report', str(root)]) == 0
    output = capsys.readouterr().out
    assert 'chip=3/3 hold=4/4 laser=5/5 OK' in output
    assert 'json: chip=1/1 hold=1/1 laser=1/1 valid=1/1' in output
    assert main(['sdvxin', str(tmp_path / 'missing')]) == 1


CORPUS = Path(__file__).resolve().parents[1] / 'corpus' / 'sdvxin'


@pytest.fixture(scope='module')
def corpus_reports():
    paths = sorted(CORPUS.glob('*/*/meta.json'))
    if not paths:
        pytest.skip('local sdvx.in corpus is absent')
    pytest.importorskip('numpy')
    pytest.importorskip('PIL')
    return [decode_report(path.parent) for path in paths]


def test_corpus_all_charts_load_and_validate(corpus_reports):
    assert not [(r['key'], r['errors']) for r in corpus_reports if r['errors']]


def test_corpus_json_chip_counts(corpus_reports):
    rows = [r for r in corpus_reports if r['kind'] == 'json']
    if not rows:
        pytest.skip('no local JSON charts')
    assert all(r['matches']['chip'] for r in rows)


def test_corpus_image_chip_counts(corpus_reports):
    rows = [r for r in corpus_reports if r['kind'] == 'image']
    if not rows:
        pytest.skip('no local image charts')
    misses = [(r['key'], r['decoded']['chip'], r['official']['chip'])
              for r in rows if not r['matches']['chip']]
    assert len(misses) / len(rows) <= 0.2, misses
    assert all(abs(d - o) <= max(3, o * 0.005) for _, d, o in misses), misses


def test_corpus_hold_and_laser_counts(corpus_reports):
    rows = [r for r in corpus_reports if r['kind'] == 'image']
    if not rows:
        pytest.skip('no local image charts')
    for kind in ('hold', 'laser'):
        rate = sum(r['matches'][kind] for r in rows) / len(rows)
        assert rate >= 0.8, (kind, [(r['key'], r['decoded'][kind], r['official'][kind])
                                    for r in rows if not r['matches'][kind]])


@pytest.mark.parametrize('level,group', [(17.4, '17'), (17.5, '18'), (18.9, '18')])
def test_decimal_level_survives_cli_decode(json_chart, tmp_path, level, group):
    from ksmauto.lint import level_group

    path = json_chart / 'meta.json'
    meta = json.loads(path.read_text())
    meta['level'] = level
    path.write_text(json.dumps(meta))
    output = tmp_path / 'decoded.kson'
    assert main(['sdvxin', str(json_chart), '-o', str(output)]) == 0
    c = load_kson(output)
    assert c['meta']['level'] == level
    assert level_group(c['meta']['level']) == group
    assert not validate(c)
