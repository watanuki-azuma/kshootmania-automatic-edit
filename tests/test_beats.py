import json
import sys
from types import SimpleNamespace

import pytest

from ksmauto.beats import fold_bpm, tempo_map


def _times(bpms, counts=None, offset=0.49):
    beats, downbeats = [], [offset]
    for bpm, count in zip(bpms, counts or [4] * len(bpms)):
        start = downbeats[-1]
        beats.extend(start + i * 60 / bpm for i in range(count))
        downbeats.append(start + count * 60 / bpm)
    return beats, downbeats


def test_constant():
    a = tempo_map(*_times([140] * 12))
    assert a['segments'] == [[0, 140, 4]]
    assert a['offset_ms'] == 490
    assert a['warnings'] == []


def test_step():
    a = tempo_map(*_times([140] * 11 + [190] * 20))
    assert a['tempo_arg'] == '0:140,11:190'


def test_half_tempo():
    beats, downbeats = _times([140] * 11 + [95] * 20)
    a = tempo_map(beats, downbeats)
    assert a['segments'] == [[0, 140, 4], [11, 190, 4]]
    assert a['downbeats'] == downbeats
    assert any('octave' in w for w in a['warnings'])


def test_tracking_octave_change_is_not_tempo_change():
    a = tempo_map(*_times([190] * 4 + [95] * 8))
    assert a['segments'] == [[0, 190, 4]]


def test_fermata():
    a = tempo_map(*_times([140] * 4 + [70] + [140] * 5))
    assert a['segments'] == [[0, 140, 4]]
    assert any(w.startswith('m4: ') and 'fermata' in w for w in a['warnings'])


def test_meter():
    a = tempo_map(*_times([150] * 6, [4] * 3 + [3] * 3))
    assert a['segments'] == [[0, 150, 4]]
    assert any('time signature' in w for w in a['warnings'])


@pytest.mark.parametrize('beats,downbeats', [([], []), ([0, 1], [0, 1]),
                                          ([0, 0, 1], [0, 1, 2]), ([float('nan')], [0, 1, 2])])
def test_bad_times(beats, downbeats):
    with pytest.raises(ValueError):
        tempo_map(beats, downbeats)


def test_fold():
    assert fold_bpm(95) == 190
    assert fold_bpm(240) == 120
    with pytest.raises(ValueError):
        fold_bpm(100, 120, 150)


def test_cli_missing(monkeypatch, capsys):
    from ksmauto.beats import main
    monkeypatch.setattr('ksmauto.beats.importlib.util.find_spec', lambda name: None)
    assert main(['song.ogg', '-o', 'unused.json']) == 1
    assert 'not installed: uv sync --extra beats' in capsys.readouterr().err


def test_cli_model_cpu(monkeypatch, tmp_path):
    from ksmauto.beats import track
    calls = []

    class Model:
        def __init__(self, **kw):
            calls.append(kw)

        def __call__(self, audio):
            beats, downbeats = _times([140] * 4)
            return SimpleNamespace(tolist=lambda: beats), SimpleNamespace(tolist=lambda: downbeats)

    monkeypatch.setitem(sys.modules, 'beat_this.inference', SimpleNamespace(File2Beats=Model))
    assert track('song.ogg', 'small0')['tempo_arg'] == '0:140'
    assert calls == [{'checkpoint_path': 'small0', 'device': 'cpu', 'dbn': False}]


def test_ritardando_is_warning():
    a = tempo_map(*_times([150, 148, 146, 144, 142, 140, 138, 136]))
    assert a['segments'][0][0] == 0
    assert any('ritardando' in w for w in a['warnings'])


@pytest.mark.parametrize('bounds', [(float('inf'), 240), (120, float('inf')), (0, 240), (240, 120)])
def test_bad_bounds(bounds):
    with pytest.raises(ValueError):
        tempo_map(*_times([140] * 4), *bounds)


def test_unstable_transition_keeps_measure_count():
    # Song-like: 11 bars of 140, a messy changeover, then 190 tracked at half tempo.
    beats, downbeats = _times([140] * 11 + [95] * 20, offset=0.486)
    cut = [t for t in beats if not 17.0 < t < 21.0] + [17.3, 17.9, 18.2, 19.9, 20.3]
    a = tempo_map(sorted(cut), sorted([d for d in downbeats if not 17.0 < d < 21.0] + [18.1]))
    assert a['tempo_arg'] == '0:140,11:190'
    assert a['offset_ms'] == 486
    assert any('unstable' in w for w in a['warnings'])


def test_offbeat_tracking_is_skipped():
    beats, downbeats = _times([140] * 12)
    beats = [t + 0.21 if 4 <= i < 12 else t for i, t in enumerate(beats)]
    assert tempo_map(beats, downbeats)['tempo_arg'] == '0:140'


@pytest.mark.parametrize('bpms,arg', [([140] * 8 + [210] * 8, '0:140,8:210'),
                                      ([140] * 8 + [280] * 8, '0:140,8:140'),
                                      ([140] * 8 + [142] * 8, '0:141')])
def test_change_at_bar_line(bpms, arg):
    a = tempo_map(*_times(bpms))
    assert a['tempo_arg'] == arg
    assert any('octave' in w for w in a['warnings']) == (bpms[-1] == 280)


def test_phase_jump_is_not_dropped():
    p = 60 / 140
    beats = [i * p for i in range(32)] + [32 * p + .2 + i * p for i in range(32)]
    downbeats = [4 * i * p for i in range(8)] + [32 * p + .2 + 4 * i * p for i in range(9)]
    a = tempo_map(beats, downbeats)
    assert len(a['segments']) == 2
    assert any('ms off' in w for w in a['warnings'])
