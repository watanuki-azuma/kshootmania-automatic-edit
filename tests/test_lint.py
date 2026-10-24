from pathlib import Path

from ksmauto.ksh import load_ksh
from ksmauto.lint import _hands_for_buttons, lint, stats

GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"


def _chart(bt=None, fx=None, laser=None, bpm=120.0):
    return {
        "format_version": 1,
        "meta": {"title": "t", "artist": "", "chart_author": "", "difficulty": 0, "level": 1, "disp_bpm": "120"},
        "beat": {"bpm": [[0, bpm]]},
        "note": {"bt": bt or [[], [], [], []], "fx": fx or [[], []], "laser": laser or [[], []]},
    }


def test_hands_for_buttons():
    assert _hands_for_buttons([("bt", 1), ("bt", 2)]) == 1
    assert _hands_for_buttons([("fx", 0), ("fx", 1)]) == 1
    assert _hands_for_buttons([("bt", 0), ("bt", 3)]) == 2
    assert _hands_for_buttons([("bt", 0), ("fx", 1)]) == 2


def test_fast_jack():
    c = _chart(bt=[[0, 30], [], [], []], bpm=120.0)  # 30 pulses = 62.5 ms at 120 BPM
    assert [f.rule for f in lint(c)] == ["fast-jack"]


def test_hand_overload_needs_moving_knob():
    moving = [[0, [[0, 0.0], [960, 1.0]]]]
    still = [[0, [[0, 0.5], [960, 0.5]]]]
    c = _chart(bt=[[240], [], [], [240]], laser=[moving, []])
    assert [f.rule for f in lint(c)] == ["hand-overload"]
    c = _chart(bt=[[240], [], [], [240]], laser=[still, []])
    assert lint(c) == []


def test_stats_on_gram():
    s = stats(load_ksh(GRAM))
    assert s["bt_chips"] > 100 and s["slams"] > 0
    assert 10 <= s["level_estimate"] <= 20
