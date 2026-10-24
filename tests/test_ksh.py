"""Regression cases adapted from libkson TestKshIO.cpp and importer branches."""

from pathlib import Path

import pytest

from ksmauto.ksh import load_ksh, parse_ksh
from ksmauto.kson import load_kson, normalize, validate


FIXTURES = Path(__file__).parent / "fixtures" / "libkson"
CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "official"


def chart(body="0000|00|--\n--", header="", version="170"):
    return parse_ksh(f"title=Test\nartist=Artist\neffect=Author\nt=120\nver={version}\n{header}\n--\n{body}\n")


def test_gram_golden():
    actual = normalize(load_ksh(FIXTURES / "Gram_ex.ksh"))
    expected = load_kson(FIXTURES / "Gram_ex.kson")
    # The fixture records the original converter's identity. A new importer
    # cannot truthfully claim either of these generator provenance values.
    differences = {
        "editor.app_name": "ksh2kson",
        "editor.app_version": "0.1.0+31da65c",
    }
    for path, value in differences.items():
        parent, key = path.split(".")
        assert expected[parent].pop(key) == value
        assert key not in actual.get(parent, {})
    assert actual == normalize(expected)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("Gram_*.ksh")), ids=lambda p: p.name)
def test_gram_validates(path):
    assert not [i for i in validate(load_ksh(path)) if i.level == "error"]


def test_official_corpus():
    if not CORPUS.exists():
        pytest.skip("Local corpus is absent")
    files = sorted(CORPUS.rglob("*.ksh"))
    assert files, "Corpus directory exists but contains no KSH charts"
    for path in files:
        assert not [i for i in validate(load_ksh(path)) if i.level == "error"], str(path)


@pytest.mark.parametrize("version,compat,bpm", [("130", "", 65535), ("120", "", 100000),
                                              ("171", "", 65535), ("160", "120", 100000)])
def test_bpm_version_limit(version, compat, bpm):
    c = chart(header=f"t=100000\nver_compat={compat}", version=version)
    assert c["beat"]["bpm"] == [[0, bpm]]


@pytest.mark.parametrize("version,compat,expected", [("170", "120", "120"), ("171", "", "171"),
                                                    ("200", "", None)])
def test_version_compat(version, compat, expected):
    c = chart(header=f"ver_compat={compat}", version=version)
    assert c["compat"].get("ksh_version") == expected


def test_bpm_and_time_signature():
    c = chart("beat=3/4\n0000|00|--\nt=180\n0000|00|--\n--\nbeat=7/8\n1000|00|--\n--")
    assert c["beat"]["bpm"] == [[0, 120], [360, 180]]
    assert c["beat"]["time_sig"] == [[0, [3, 4]], [1, [7, 8]]]
    assert c["note"]["bt"][0] == [720]


def test_display_bpm_range_uses_first_body_bpm():
    c = chart("0000|00|--\nt=150\n0000|00|--\n--", "t=100-200")
    assert c["meta"]["disp_bpm"] == "100-200"
    assert c["beat"]["bpm"] == [[0, 150]]


def test_scroll_immediate_change():
    c = chart("0000|00|--\nscroll_speed=1.0\nscroll_speed=3.0\n0000|00|--\n--")
    assert c["beat"]["scroll_speed"] == [[0, 1], [480, [1, 3]]]


@pytest.mark.parametrize("parameter", ["zoom_top", "zoom_bottom", "zoom_side", "center_split", "rotation_deg", "scroll_speed"])
@pytest.mark.parametrize("curve_first", [True, False])
def test_curve_before_or_after_parameter(parameter, curve_first):
    lines = [f"{parameter}=100", f"{parameter}_curve=0.3;0.7"]
    if curve_first:
        lines.reverse()
    c = chart("\n".join([*lines, "0000|00|--", "--"]))
    points = c["beat"]["scroll_speed"] if parameter == "scroll_speed" else c["camera"]["cam"]["body"][parameter]
    assert points == [[0, 100, [0.3, 0.7]]]


def test_curve_different_pulse_ignored():
    c = chart("zoom_top_curve=0.3;0.7\n0000|00|--\nzoom_top=100\n0000|00|--\n--")
    assert c["camera"]["cam"]["body"]["zoom_top"] == [[480, 100]]


@pytest.mark.parametrize("body,expected", [
    ("tilt=big", "bigger"), ("tilt=keep", "keep_bigger"),
    ("tilt=0.1\ntilt=0.5", [0.1, 0.5]),
    ("tilt=0.8\ntilt=normal", [0.8, "normal"]),
    ("tilt=0.1\ntilt_curve=0.3;0.7", [0.1, [0.3, 0.7]]),
    ("tilt=0.1\ntilt_curve=0.3;0.7\ntilt=0.5", [[0.1, 0.5], [0.3, 0.7]]),
    ("tilt=0.1\ntilt=normal\ntilt_curve=0.3;0.7", [[0.1, "normal"], [0.3, 0.7]]),
])
def test_tilt_forms(body, expected):
    assert chart(body + "\n0000|00|--\n--")["camera"]["tilt"] == [[0, expected]]


def test_legacy_manual_tilt_scales_entire_chart():
    c = chart("tilt=5\n0000|00|--\ntilt=10\n0000|00|--\n--", version="160")
    assert c["camera"]["tilt"] == [[0, 7], [480, 14]]


@pytest.mark.parametrize("version,value,expected", [("160", "301", []), ("167", "301", [[0, 301]]),
                                                    ("160", "12345", []), ("167", "12345", [[0, 12345]])])
def test_zoom_legacy_limit(version, value, expected):
    c = chart(f"zoom_top={value}\n0000|00|--\n--", version=version)
    assert c["camera"]["cam"]["body"]["zoom_top"] == expected


@pytest.mark.parametrize("splits,slams", [(16, False), (32, True), (64, True)])
def test_slam_threshold(splits, slams):
    c = chart("\n".join(["0000|00|0-", "0000|00|o-", *(["0000|00|--"] * (splits - 2)), "--"]))
    points = c["note"]["laser"][0][0][1]
    assert points == ([[0, [0, 1]]] if slams else [[0, 0], [60, 1]])


def test_chained_slams_and_laser_curve():
    c = chart("\n".join(["laser_l_curve=0.2;0.8", "0000|00|0-", "0000|00|o-", "0000|00|0-",
                            *(["0000|00|--"] * 29), "--"]))
    assert c["note"]["laser"][0] == [[0, [[0, [0, 1], [0.2, 0.8]], [30, [1, 0]]]]]


def test_wide_laser_zero_positions_and_connections():
    c = chart("laserrange_l=2x\n0000|00|C-\n0000|00|:-\n0000|00|b-\n0000|00|--\n--")
    assert c["note"]["laser"][0] == [[0, [[0, 0.25], [480, 0.75]], 2]]


def test_buttons_across_measure_boundary():
    c = chart("2000|10|--\n--\n2000|10|--\n1000|20|--\n--\n0000|00|--\n--")
    assert c["note"]["bt"][0] == [[0, 1440], 1440]
    assert c["note"]["fx"][0] == [[0, 1440], 1440]


@pytest.mark.parametrize("effect,params", [
    ("Retrigger", {"wave_length": "1/8"}), ("Gate;16", {"wave_length": "1/16"}),
    ("Wobble", {"wave_length": "1/12"}), ("PitchShift;-5", {"pitch": "-5"}),
    ("BitCrusher;12", {"reduction": "12samples"}), ("TapeStop;40", {"speed": "40%"}),
    ("Echo;8;70", {"wave_length": "1/8", "feedback_level": "70%"}),
    ("Echo", {"wave_length": "1/4", "feedback_level": "60%"}), ("Flanger", {}),
])
def test_fx_parameters(effect, params):
    c = chart(f"fx-l={effect}\n0000|10|--\n0000|00|--\n--")
    events = c["audio"]["audio_effect"]["fx"]["long_event"]
    assert next(iter(events.values())) == [[[0, params]], []]


def test_late_effect_definition_and_parameter_names():
    c = chart("fx-l=Custom;16\n0000|10|--\n0000|00|--\n--\n"
              "#define_fx Custom type=Retrigger;waveLength=1/4;updatePeriod=0;volume=80%")
    fx = c["audio"]["audio_effect"]["fx"]
    assert fx["def"] == [["Custom", {"type": "retrigger", "v": {"wave_length": "1/4", "update_period": "0", "vol": "80%"}}]]
    assert fx["long_event"]["Custom"][0] == [[0, {"wave_length": "1/16"}]]


def test_legacy_fx_char_parameter_change_and_clear():
    c = chart("0000|S0|--\nfx-l_param1=16\n0000|S0|--\n0000|10|--\n0000|00|--\n--")
    fx = c["audio"]["audio_effect"]["fx"]["long_event"]
    assert fx["retrigger"][0] == [[0, {"wave_length": "1/8"}], [240, {"wave_length": "1/16"}]]
    assert fx[""][0] == [[480, {}]]
    assert c["note"]["fx"][0] == [[0, 720]]


@pytest.mark.parametrize("kind,name,result", [("fx", "Retrigger", "retrigger"), ("filter", "peak", "peaking_filter"),
                                             ("filter", "Custom", "Custom")])
def test_preset_param_change_import(kind, name, result):
    c = chart(f"{kind}:{name}:waveLength=1/24\n0000|00|--\n--")
    effect = c["audio"]["audio_effect"]["fx" if kind == "fx" else "laser"]
    assert effect["param_change"] == {result: {"wave_length": [[0, "1/24"]]}}


def test_duplicate_effect_definition_keeps_order():
    c = chart("0000|00|--\n--\n#define_fx A type=Gate\n#define_fx B type=Phaser\n#define_fx A type=Echo")
    assert c["audio"]["audio_effect"]["fx"]["def"] == [
        ["A", {"type": "echo", "v": {}}], ["B", {"type": "phaser", "v": {}}]]


def test_filter_legacy_names_gain_and_prerendered_audio():
    c = chart("filtertype=fx\npfiltergain=20\n0000|00|--\nfiltertype=fx;bitc\n0000|00|--\n--",
              "m=main.ogg;filter.ogg;p.ogg;both.ogg")
    laser = c["audio"]["audio_effect"]["laser"]
    assert laser["pulse_event"] == {"fx": [0], "fx;bitcrusher": [480]}
    assert laser["def"] == [["fx", {"type": "switch_audio", "v": {"filename": "filter.ogg"}}],
                            ["fx;bitcrusher", {"type": "bitcrusher"}]]
    assert laser["legacy"]["filter_gain"] == [[0, 0.2]]
    assert c["audio"]["bgm"]["legacy"]["fp_filenames"] == ["filter.ogg", "p.ogg", "both.ogg"]


def test_key_sounds_and_stop():
    c = chart("fx-l_se=clap;80\nchokkakuse=down\nchokkakuvol=35\nstop=48\n"
              "0000|20|0-\n0000|00|o-\n--")
    assert c["audio"]["key_sound"]["fx"]["chip_event"] == {"clap": [[[0, {"vol": 0.8}]], []]}
    assert c["audio"]["key_sound"]["laser"]["slam_event"] == {"down": [0]}
    assert c["audio"]["key_sound"]["laser"]["vol"] == [[0, 0.35]]
    assert c["beat"]["stop"] == [[0, 240]]


@pytest.mark.parametrize("suffix,name,event", [("@(192", "spin", [0, -1, 960]),
                                               ("@>96", "half_spin", [0, 1, 480]),
                                               ("S>128;100;3;1", "swing", [0, 1, 640, {"scale": 100, "repeat": 3, "decay_order": 1}])])
def test_camera_patterns(suffix, name, event):
    c = chart(f"0000|00|--{suffix}\n--")
    assert c["camera"]["cam"]["pattern"]["laser"]["slam_event"] == {name: [event]}


@pytest.mark.parametrize("version,separator", [("160", "/"), ("166", ";")])
def test_background_layer_and_movie(version, separator):
    c = chart(header=f"bg=a;b\nlayer=layer{separator}-100{separator}1\nv=movie.mp4\nvo=-20", version=version)
    assert c["bg"]["legacy"] == {"bg": [{"filename": "a"}, {"filename": "b"}],
                                    "layer": {"filename": "layer", "duration": -100,
                                              "rotation": {"tilt": True, "spin": False}},
                                    "movie": {"filename": "movie.mp4", "offset": -20}}


def test_comments_multiline_and_same_pulse():
    c = chart("//first\\nsecond\n//third\n0000|00|--\n--", "//header")
    assert c["editor"]["comment"] == [[0, "header"], [0, "first\nsecond"], [0, "third"]]


def test_unknown_lines_and_options():
    c = chart(";line\next=first=second\n0000|00|--\n;option=10\n0000|00|--\n--", "extra=header\n;header")
    assert c["compat"]["ksh_unknown"] == {
        "meta": {"extra": "header"}, "option": {"ext": [[0, "first=second"]], ";option": [[480, "10"]]},
        "line": [[0, ";header"], [0, ";line"]]}


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp932"])
def test_encoding(tmp_path, encoding):
    path = tmp_path / "chart.ksh"
    path.write_bytes("title=日本語\nt=120\n--\n0000|00|--\n--\n".encode(encoding))
    assert load_ksh(path)["meta"]["title"] == "日本語"


def test_legacy_bgm_volume_and_level_clamp():
    c = chart(header="level=99\nmvol=50", version="100")
    assert c["audio"]["bgm"]["vol"] == 0.3
    assert c["meta"]["level"] == 20


@pytest.mark.parametrize("text", ["title=X", "artist=X\n--\n", "title=X\n--\nbeat=0/4\n"])
def test_invalid_chart(text):
    with pytest.raises(ValueError):
        parse_ksh(text)
