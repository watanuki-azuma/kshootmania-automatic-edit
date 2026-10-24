"""Draft syntax, diagnostics, CLI, and source-chart round trips."""

import builtins
import copy
import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from ksmauto.cli import main
from ksmauto.draft import DraftError, _format_beat, compile_draft, decompile
from ksmauto.ksh import load_ksh
from ksmauto.kson import load_kson, normalize


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "libkson"
CORPUS = ROOT / "corpus" / "official"


def compile_ok(body="", header="", base=None):
    result, errors = compile_draft(f"title: Test\nbpm: 150\n{header}\n{body}", base)
    assert not errors
    return result


def test_header_defaults():
    chart = compile_ok()
    assert chart["meta"] == {"title": "Test", "artist": "", "chart_author": "",
                             "difficulty": 2, "level": 1, "disp_bpm": "150"}
    assert chart["beat"] == {"bpm": [[0, 150]], "time_sig": [[0, [4, 4]]]}
    assert chart["note"] == {"bt": [[], [], [], []], "fx": [[], []], "laser": [[], []]}


def test_all_headers_and_quoted_comments():
    chart = compile_ok(header='''title: "日本語 # song"
artist: An Artist # trailing comment
chart_author: "An Author"
difficulty: 3
level: 20
jacket: jacket.png
audio: "audio file.ogg"
offset: -120
volume: 0.75
preview: 59050 12573
time_sig: 6/8
disp_bpm: 100-200''')
    assert chart["meta"] == {"title": "日本語 # song", "artist": "An Artist",
                             "chart_author": "An Author", "difficulty": 3, "level": 20,
                             "jacket_filename": "jacket.png", "disp_bpm": "100-200"}
    assert chart["audio"]["bgm"] == {"filename": "audio file.ogg", "offset": -120,
                                     "vol": 0.75, "preview": {"offset": 59050, "duration": 12573}}
    assert chart["beat"]["time_sig"] == [[0, [6, 8]]]


@pytest.mark.parametrize("beat,y", [("2", 480), ("1.5", 360), ("3/4", 180),
                                    ("2+1/3", 560), ("m12:2.5", 12120), ("1/7", 34)])
def test_positions(beat, y):
    assert compile_ok(f"@m0\n{beat} A")["note"]["bt"][0] == [y]


def test_chips_multilane_and_mixed_longs():
    notes = compile_ok("@m0\n0 A B C D L R\n1 A B~1/2 R\n2 C~m2:1\n3 D~2")["note"]
    assert notes["bt"] == [[0, 240], [0, [240, 120]], [0, [480, 1680]], [0, [720, 480]]]
    assert notes["fx"] == [[0], [0, 240]]


def test_out_of_order_notes_timing_and_labels():
    chart = compile_ok('''@m3 "later"
3 A
bpm 2 200
time_sig 7/8
0 A
@m0 "intro"
2 B
bpm 1 125
@m1
time_sig 6/8
5 L~2
@m2
5 R~m3:1''')
    assert chart["beat"]["bpm"] == [[0, 150], [240, 125], [2640, 200]]
    assert chart["beat"]["time_sig"] == [[0, [4, 4]], [1, [6, 8]], [3, [7, 8]]]
    assert chart["note"]["bt"][0] == [2400, 2760]
    assert chart["note"]["fx"] == [[[1560, 240]], [[2280, 240]]]
    assert chart["editor"]["comment"] == [[0, "intro"], [2400, "later"]]
    assert chart["meta"]["disp_bpm"] == "125-200"


def test_body_zero_signature_overrides_header():
    chart = compile_ok("@m0\n5 A\ntime_sig 6/8", header="time_sig: 3/4")
    assert chart["beat"]["time_sig"] == [[0, [6, 8]]]
    assert chart["note"]["bt"][0] == [600]


@pytest.mark.parametrize("lane,index,width", [("l", 0, []), ("r", 1, []),
                                            ("l2", 0, [2]), ("r2", 1, [2])])
def test_laser_sections(lane, index, width):
    chart = compile_ok(f"@m0\n0 {lane} 0 +2:1 +1:1>0 +1/2:0.5")
    assert chart["note"]["laser"][index] == [[0, [[0, 0], [480, 1], [720, [1, 0]],
                                                               [840, 0.5]], *width]]


def test_laser_slam_only_and_compound_fraction_deltas():
    notes = compile_ok("@m0\n0 l 0>1\n1 r 0 +1/3:0.5 +2+1/3:1")["note"]
    assert notes["laser"] == [[[0, [[0, [0, 1]]]]],
                              [[240, [[0, 0], [80, 0.5], [640, 1]]]]]


def test_lasers_use_initial_measure_beat_unit_across_changes():
    chart = compile_ok("@m0\ntime_sig 6/8\n5 l 0 +3:1\n@m1\ntime_sig 4/4")
    assert chart["note"]["laser"][0] == [[600, [[0, 0], [360, 1]]]]
    text, _ = decompile(chart)
    assert "5 l 0 +3:1" in text
    assert compile_draft(text)[0]["note"] == chart["note"]


def test_copy_inclusive_measures_and_file_order():
    chart = compile_ok('''@m8
0 A L~6
0 l2 0.25>0.75 +6:1
@m11
3 B
@m12
0 C
copy m8-11 -> m24 mirror
copy m24-27 -> m40
@m8
1 D''')
    notes = chart["note"]
    assert notes["bt"][0] == [7680]
    assert notes["bt"][1] == [11280]
    assert notes["bt"][2] == [11520, 26640, 42000]
    assert notes["bt"][3] == [7920, 23040, 38400]
    assert notes["fx"][1] == [[23040, 1440], [38400, 1440]]
    assert notes["laser"][1] == [[23040, [[0, [0.75, 0.25]], [1440, 0]], 2],
                                  [38400, [[0, [0.75, 0.25]], [1440, 0]], 2]]


def test_copy_half_open_beats_and_whole_extending_notes():
    chart = compile_ok('''@m8
1 A
2 B~8
3 C
2 r 0 +8:1
@m9
0 D
copy m8:2-m9:0 -> m30:2''')
    assert chart["note"]["bt"] == [[7920], [[8160, 1920], [29280, 1920]],
                                      [8400, 29520], [8640]]
    assert chart["note"]["laser"][1][-1] == [29280, [[0, 0], [1920, 1]]]


def test_copy_same_length_different_signatures():
    chart = compile_ok("@m0\n0 A\n@m2\ntime_sig 8/8\ncopy m0-0 -> m2")
    assert chart["note"]["bt"][0] == [0, 1920]


@pytest.mark.parametrize("body,message", [
    ("@m-1", "@mN"), ("@m0 invalid", "@mN"),
    ("@m0\n4 A", "Beat must"), ("@m0\n-1 A", "Beat must"),
    ("@m0\n1/0 A", "Invalid beat"), ("@m0\nx A", "Invalid beat"),
    ("@m0\nm1:4 A", "Beat must"), ("@m0\nm1 A", "absolute position"),
    ("@m0\n0", "Expected button"), ("@m0\n0 X", "Invalid button"),
    ("@m0\n0 A~0", "length must"), ("@m0\n0 A~-1", "length must"),
    ("@m0\n1 A~m0:0", "length must"), ("@m0\n0 A~", "Invalid beat"),
    ("@m0\n0 l", "initial value"), ("@m0\n0 l 2", "Laser values"),
    ("@m0\n0 r -0.1", "Laser values"), ("@m0\n0 l 0>2", "Laser values"),
    ("@m0\n0 l 0 +0:1", "DT must"), ("@m0\n0 l 0 +-1:1", "DT must"),
    ("@m0\n0 l 0 +1:-1", "Laser values"), ("@m0\n0 l 0 bad", "laser point"),
    ("@m0\n0 l 0>1>0", "V>VF"), ("@m0\n0 l nan", "finite"),
    ("@m0\nbpm 0 0", "BPM must"), ("@m0\nbpm 0 inf", "finite"),
    ("@m0\nbpm 0", "Expected bpm"), ("@m0\ntime_sig 0/4", "Time signature"),
    ("@m0\ntime_sig 4", "Time signature"), ("@m0\ntime_sig 4/4 extra", "Expected time_sig"),
    ("@m0\ncopy m0-0 => m1", "Expected copy"),
    ("@m0\ncopy m1-0 -> m2", "positive length"),
    ("@m0\ncopy m1:1-m1:1 -> m2", "positive length"),
    ("@m0\ncopy bad -> m1", "copy range"),
    ("@m0\ncopy m0-0 -> bad", "destination"),
    ("@m0\ncopy m0-0 -> m1 flip", "Expected copy"),
    ("@m0\n0 A\n@m1\ntime_sig 3/4\ncopy m0-0 -> m1", "different measure lengths"),
    ("@m0\ncopy m0-1 -> m2\n@m3\ntime_sig 3/4", "different measure lengths"),
])
def test_body_errors_have_source_line(body, message):
    text = f"title: Test\nbpm: 150\n{body}"
    _, errors = compile_draft(text)
    expected_line = 3 + next(i for i, line in enumerate(body.splitlines())
                             if line.startswith("copy") or (i == len(body.splitlines()) - 1))
    assert any(e.line == expected_line and message in e.message for e in errors), errors
    assert all(e.col >= 1 for e in errors if e.line)


@pytest.mark.parametrize("header,message", [
    ("unknown: value", "Unknown header"), ("difficulty: 4", "Difficulty"),
    ("difficulty: extended", "invalid literal"), ("level: 0", "Level"),
    ("offset: 1.5", "invalid literal"), ("volume: nan", "finite"),
    ("preview: -1 2", "Preview"), ("preview: 1", "Preview"),
    ("bpm: -1", "BPM must"), ("time_sig: 0/4", "Time signature"),
    ('title: "broken', "Unterminated"), ("not a header", "Expected key"),
])
def test_header_errors_have_source_line(header, message):
    _, errors = compile_draft(f"title: Test\nbpm: 150\n{header}\n@m0")
    assert any(e.line == 3 and message in e.message for e in errors), errors


def test_required_headers_and_validation_errors():
    _, errors = compile_draft("@m0\n0 A")
    assert any("title" in e.message and e.line == 1 for e in errors)
    assert any("bpm" in e.message and e.line == 1 for e in errors)
    assert any(e.line == e.col == 0 and "Required field" in e.message for e in errors)
    assert DraftError(2, 3, "bad").line == 2


@pytest.mark.parametrize("first,second", [
    ("0 A", "0 A"), ("0 A~2", "1 A"), ("1 A", "0 A~2"),
    ("0 A~2", "1 A~2"), ("1 A~2", "0 A~2"),
    ("0 l 0 +2:1", "1 l2 0>1"), ("1 r 0>1", "0 r 0 +2:1"),
    ("0 r 0>1", "0 r 1>0"),
])
def test_overlaps_point_to_later_source_line(first, second):
    _, errors = compile_draft(f"title: T\nbpm: 150\n@m0\n{first}\n{second}")
    assert any(e.line == 5 and "overlap" in e.message and "line 4" in e.message for e in errors)


@pytest.mark.parametrize("tail,later", [("copy m0-0 -> m1\n0 A", 7),
                                        ("0 A\ncopy m0-0 -> m1", 7)])
def test_copy_overlap_origin(tail, later):
    _, errors = compile_draft("title: T\nbpm: 150\n@m0\n0 A\n@m1\n" + tail)
    assert any(e.line == later and "overlap" in e.message for e in errors)


def test_touching_endpoints_are_allowed():
    compile_ok("@m0\n0 A~1\n1 A\n0 l 0 +1:1\n1 l 1>0")


def test_all_errors_collected_and_columns():
    _, errors = compile_draft("title: T\nbpm: 150\nunknown: x\n@m0\n  0 X Y\n1 l 2 +0:1 +1:-1\n4 A\n2 B~0")
    assert {e.line for e in errors if e.line} == {3, 5, 6, 7, 8}
    assert {(e.line, e.col) for e in errors} >= {(5, 5), (5, 7), (6, 5), (6, 7), (6, 12)}


def test_example_in_document():
    example = (ROOT / "docs" / "draft-format.md").read_text().split("## 例")[1].split("```")[1]
    chart, errors = compile_draft(example)
    assert not errors
    assert chart["meta"]["title"] == "Example"
    assert chart["note"]["bt"][3] == [1680, 2400, 2880, 3840]


def test_base_is_copied_and_other_fields_preserved():
    base = compile_ok("@m0\n0 A", "artist: Original\naudio: old.ogg\ntime_sig: 3/4")
    base.update({"camera": {"tilt": [[0, "biggest"]]}, "bg": {"filename": "bg.png"}})
    base["beat"]["scroll_speed"] = [[0, 2]]
    base["audio"]["audio_effect"] = {"laser": {"peaking_filter_delay": 10}}
    before = copy.deepcopy(base)
    chart = compile_ok("@m1\n0 B\nbpm 1 200", "title: Updated", base)
    assert base == before
    assert chart["note"]["bt"] == [[], [960], [], []]
    assert chart["beat"] == {"bpm": [[0, 150], [1200, 200]], "time_sig": [[0, [4, 4]]],
                             "scroll_speed": [[0, 2]]}
    assert chart["meta"]["title"] == "Updated"
    assert chart["meta"]["artist"] == "Original"
    for key in ("camera", "bg", "audio"):
        assert chart[key] == base[key]


@pytest.mark.parametrize("value,expected", [(Fraction(2), "2"), (Fraction(3, 2), "1.5"),
                                          (Fraction(1, 4), "0.25"), (Fraction(1, 8), "0.125"),
                                          (Fraction(1, 3), "1/3"), (Fraction(7, 3), "2+1/3"),
                                          (Fraction(1, 16), "1/16")])
def test_beat_formatting(value, expected):
    assert _format_beat(value) == expected


def test_decompile_grouping_order_empty_measures_and_crossing_lengths():
    chart = compile_ok('''@m0 "a # label"
2 R L D C B~5 A
1 l2 0 +1/3:0.5 +2+1/3:1>0
bpm 3 200
@m2
time_sig 7/8
@m4 "end"''')
    text, warnings = decompile(chart)
    assert not warnings
    assert text.count("@m") == 3
    assert '@m0 "a # label"' in text
    assert "2 A B~5 C D L R" in text
    assert text.index("1 l2") < text.index("2 A") < text.index("bpm 3")
    assert "1 l2 0 +1/3:0.5 +2+1/3:1>0" in text
    assert "@m2\ntime_sig 7/8" in text
    actual, errors = compile_draft(text)
    assert not errors and actual == chart


def test_decompile_warnings_and_curve_dropping():
    chart = compile_ok("@m0\n0 l 0 +1:1")
    chart["note"]["laser"][0][0][1][0].append([0.2, 0.8])
    chart["beat"].update({"scroll_speed": [[0, 2]], "stop": [[240, 120]]})
    chart.update({"camera": {"tilt": [[0, "bigger"]]}, "bg": {"filename": "bg.png"}})
    chart["audio"] = {"audio_effect": {"laser": {"peaking_filter_delay": 0}},
                      "key_sound": {"laser": {"vol": [[0, 0.5]]}}}
    text, warnings = decompile(chart)
    assert set(warnings) == {"laser curves", "scroll_speed", "stop", "camera", "audio effects", "key sounds", "bg"}
    for warning in warnings:
        assert f"# unsupported: {warning}\n" in text
    rebuilt, errors = compile_draft(text, base=chart)
    assert not errors
    assert rebuilt["note"]["laser"][0][0][1][0] == [0, 0]
    for key in ("camera", "bg", "audio"):
        assert rebuilt[key] == chart[key]


def test_decompile_laser_value_formatting():
    chart = compile_ok("@m0\n0 r 0.12345>1 +1:0.5 +1:0")
    text, _ = decompile(chart)
    assert "0 r 0.123>1 +1:0.5 +1:0" in text


def test_base_retains_equivalent_explicit_note_shapes():
    chart = normalize(compile_ok("@m0\n0 A\n0 l 0 +1:1"))
    text, _ = decompile(chart)
    rebuilt, errors = compile_draft(text, base=chart)
    assert not errors
    assert rebuilt["note"]["bt"] == chart["note"]["bt"]
    assert rebuilt["note"]["laser"][0][0] == [0, [[0, [0, 0]], [240, [1, 1]]], 1]


def test_base_comments_preserved_without_duplicating_draft_labels():
    chart = compile_ok('@m0 "intro"\n@m0 "second label"\n0 A')
    chart["editor"]["comment"].append([240, "mid-measure"])
    text, warnings = decompile(chart)
    assert text.count("@m0") == 1
    assert "multiple editor comments at one measure start" in warnings
    assert "editor comments away from measure starts" in warnings
    rebuilt, errors = compile_draft(text, base=chart)
    assert not errors
    assert rebuilt["editor"] == chart["editor"]
    updated = compile_ok('@m1 "new"', base=chart)
    assert updated["editor"]["comment"] == chart["editor"]["comment"] + [[960, "new"]]


def assert_round_trip(chart):
    original = copy.deepcopy(chart)
    text, _ = decompile(chart)
    rebuilt, errors = compile_draft(text, base=chart)
    assert not errors
    assert chart == original
    for source in (original, rebuilt):
        for lane in source["note"]["laser"]:
            for section in lane:
                section[1] = [point[:2] for point in section[1]]
    assert rebuilt["note"] == original["note"]
    for key in ("bpm", "time_sig"):
        assert rebuilt["beat"][key] == original["beat"][key]
    assert rebuilt["meta"] == original["meta"]
    return rebuilt


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("Gram_*.*sh")) + [FIXTURES / "Gram_ex.kson"],
                         ids=lambda p: p.name)
def test_gram_round_trip(path):
    assert_round_trip(load_ksh(path) if path.suffix == ".ksh" else load_kson(path))


def test_corpus_round_trip():
    if not CORPUS.exists():
        pytest.skip("Local corpus is absent")
    paths = sorted(CORPUS.rglob("*.ksh"))
    assert paths, "Corpus directory exists but contains no KSH charts"
    for path in paths:
        chart = load_ksh(path)
        try:
            assert_round_trip(chart)
        except AssertionError as exc:
            raise AssertionError(str(path)) from exc


def test_cli_compile_decompile_and_defaults(tmp_path, capsys):
    path = tmp_path / "chart.ksmd"
    path.write_text("title: CLI\nbpm: 150\n@m0\n0 A")
    assert main(["compile", str(path)]) == 0
    kson = path.with_suffix(".kson")
    assert load_kson(kson)["note"]["bt"][0] == [0]
    assert main(["decompile", str(kson)]) == 0
    assert "@m0\n0 A" in capsys.readouterr().out
    out = tmp_path / "out.ksmd"
    assert main(["decompile", str(FIXTURES / "Gram_ex.ksh"), "-o", str(out)]) == 0
    assert "unsupported:" in capsys.readouterr().err
    assert out.read_text().startswith("# unsupported:")


@pytest.mark.parametrize("base", ["Gram_ex.kson", "Gram_ex.ksh"])
def test_cli_base(tmp_path, base):
    path = tmp_path / "chart.ksmd"
    path.write_text("title: CLI\nbpm: 150\n@m0\n0 A")
    out = tmp_path / "out.kson"
    assert main(["compile", str(path), "--base", str(FIXTURES / base), "-o", str(out)]) == 0
    assert load_kson(out)["camera"]
    assert load_kson(out)["meta"]["title"] == "CLI"


def test_cli_errors_do_not_write_output(tmp_path, capsys):
    path = tmp_path / "broken.ksmd"
    path.write_text("title: CLI\nbpm: 150\n@m0\n4 A\n0 X")
    assert main(["compile", str(path)]) == 1
    err = capsys.readouterr().err
    assert f"{path}:4:1:" in err and f"{path}:5:3:" in err
    assert not path.with_suffix(".kson").exists()
    assert main(["compile", str(tmp_path / "missing.ksmd")]) == 1
    assert main(["decompile", str(tmp_path / "missing.ksh")]) == 1


def test_cli_analyze_forwards_arguments_lazily(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "ksmauto.analyze", SimpleNamespace(main=lambda args: calls.append(args) or 7))
    assert main(["analyze", "song.ogg", "--beats", "6", "-o", "out.json"]) == 7
    assert calls == [["song.ogg", "--beats", "6", "-o", "out.json"]]


def test_cli_analyze_import_failure(monkeypatch, capsys):
    original = builtins.__import__

    def no_analyze(name, *args, **kwargs):
        if name == "analyze":
            raise ImportError("missing audio dependencies")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_analyze)
    assert main(["analyze", "song.ogg"]) == 1
    assert "install the audio extra: uv sync --extra audio" in capsys.readouterr().err


def test_copy_single_measure():
    chart, errors = compile_draft("title: t\nbpm: 120\n@m1\n0 A\n1 B\ncopy m1 -> m2 mirror\n")
    assert not errors
    assert chart["note"]["bt"][3] == [960 * 2] and chart["note"]["bt"][2] == [960 * 2 + 240]
