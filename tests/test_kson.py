import copy
import json
from pathlib import Path

import pytest

from ksmauto.kson import dumps_kson, load_kson, normalize, save_kson, validate


def minimal():
    return {"format_version": 1,
            "meta": {"title": "日本語", "artist": "A", "chart_author": "B",
                     "difficulty": 2, "level": 10, "disp_bpm": "120"},
            "beat": {"bpm": [[0, 120]]}}


def test_round_trip(tmp_path):
    path = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.kson"
    c = load_kson(path)
    assert json.loads(dumps_kson(c)) == c
    output = tmp_path / "chart.kson"
    save_kson(c, output)
    assert load_kson(output) == c
    data = output.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")
    assert "坂本龍馬" in data.decode("utf-8")


def test_normalize_defaults_copy_and_idempotence():
    c = minimal()
    original = copy.deepcopy(c)
    n = normalize(c)
    assert c == original
    assert n["beat"]["time_sig"] == [[0, [4, 4]]]
    assert n["beat"]["scroll_speed"] == [[0, [1, 1], [0, 0]]]
    assert n["audio"]["bgm"] == {"vol": 1, "offset": 0, "preview": {"offset": 0, "duration": 15000}}
    assert n["camera"]["tilt"] == [[0, "normal"]]
    assert normalize(n) == n
    assert validate(n) == []


def test_normalize_shorthands():
    a = minimal()
    a["note"] = {"bt": [[0], [], [], []], "laser": [[[0, [[0, 0.5], [240, 1]]]], []]}
    b = copy.deepcopy(a)
    b["note"]["bt"][0] = [[0, 0]]
    b["note"]["laser"][0][0] = [0, [[0, [0.5, 0.5], [0, 0]], [240, [1, 1], [0, 0]]], 1]
    assert normalize(a) == normalize(b)


def test_normalize_preserves_implementation_data():
    c = minimal()
    c["impl"] = {"tool": {"selection": [], "state": {}}}
    assert normalize(c)["impl"] == c["impl"]


@pytest.mark.parametrize("compat,expected", [(None, "1/8"), ("160", "1/16"), ("200", "1/8")])
def test_normalize_effect_defaults(compat, expected):
    c = minimal()
    c["audio"] = {"audio_effect": {"fx": {"def": [["custom", {"type": "sidechain"}]]}}}
    if compat:
        c["compat"] = {"ksh_version": compat}
    n = normalize(c)
    assert n["audio"]["audio_effect"]["fx"]["def"][0][1]["v"]["release_time"] == expected


@pytest.mark.parametrize("key,value", [("level", 0), ("level", 21), ("level", True),
                                     ("difficulty", 4), ("difficulty", -1), ("title", None),
                                     ("artist", []), ("std_bpm", "120")])
def test_metadata_errors(key, value):
    c = minimal()
    c["meta"][key] = value
    assert any(i.level == "error" and i.path == f"$.meta.{key}" for i in validate(c))


@pytest.mark.parametrize("difficulty", [0, 3, "maximum"])
def test_difficulty_variants(difficulty):
    c = minimal()
    c["meta"]["difficulty"] = difficulty
    assert validate(c) == []


@pytest.mark.parametrize("key", ["format_version", "meta", "beat"])
def test_required_top_level_fields(key):
    c = minimal()
    del c[key]
    assert any(i.path == f"$.{key}" and i.level == "error" for i in validate(c))


def test_required_nested_fields():
    c = minimal()
    del c["meta"]["chart_author"]
    del c["beat"]["bpm"]
    assert {i.path for i in validate(c)} == {"$.meta.chart_author", "$.beat.bpm"}


def test_null_checked_in_extensions():
    c = minimal()
    c["impl"] = {"tool": {"arbitrary": [None]}}
    assert any(i.path == "$.impl.tool.arbitrary[0]" and "Null" in i.message for i in validate(c))


@pytest.mark.parametrize("notes", [
    {"bt": [[], []]}, {"fx": [[], [], []]}, {"laser": [[]]},
    {"bt": [[[0, 20, 40]], [], [], []]},
    {"laser": [[[0, [[10, 0.5]]]], []]},
    {"laser": [[[0, [[0, 1.1]]]], []]},
    {"laser": [[[0, [[0, [-0.1, 0.5]]]]], []]},
    {"laser": [[[0, [[0, 0.5]], 3]], []]},
    {"laser": [[[0, [[0, 0.5], [100, 1], [50, 0.5]]]], []]},
    {"laser": [[[0, [[0, 0], [200, 1]]], [100, [[0, 0], [200, 1]]]], []]},
    {"bt": [[[0, 240], 120], [], [], []]},
    {"fx": [[120, 120], []]}, {"bt": [[120, 0], [], [], []]},
])
def test_invalid_notes(notes):
    c = minimal()
    c["note"] = notes
    assert any(i.level == "error" for i in validate(c))


def test_touching_note_boundaries_allowed():
    c = minimal()
    c["note"] = {"bt": [[[0, 240], 240], [], [], []],
                 "laser": [[[0, [[0, 0], [240, 1]]], [240, [[0, 1], [240, 0]]]], []]}
    assert validate(c) == []


@pytest.mark.parametrize("beat", [
    {"bpm": [[0, 0]]}, {"bpm": []}, {"bpm": [[0, True]]},
    {"bpm": [[240, 120], [0, 180]]},
    {"bpm": [[0, 120]], "time_sig": [[2, [3, 4]], [1, [4, 4]]]},
    {"bpm": [[0, 120]], "scroll_speed": [[0, 1, [0.5]]]},
])
def test_invalid_beat(beat):
    c = minimal()
    c["beat"] = beat
    assert any(i.level == "error" for i in validate(c))


@pytest.mark.parametrize("chart", [None, [], "text", {"note": {"laser": [None, 123]}}])
def test_malformed_root_does_not_crash(chart):
    assert validate(chart)


def test_unknown_fields_warn():
    c = minimal()
    c["extension"] = 123
    assert [(i.level, i.path) for i in validate(c)] == [("warning", "$.extension")]


def test_dumps_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        dumps_kson({"value": float("nan")})


@pytest.mark.parametrize("level", [1, 17.4, 17.5, 18.9, 20])
def test_numeric_level(level):
    c = minimal()
    c["meta"]["level"] = level
    assert validate(c) == []
