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
