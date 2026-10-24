import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from ksmauto.cli import main
from ksmauto.ksh import load_ksh
from ksmauto.preview import build_preview

ROOT = Path(__file__).resolve().parents[1]


def _chart():
    return {"format_version": 1, "meta": {"title": "A </script> B", "artist": "x", "level": 17, "difficulty": 2},
            "beat": {"bpm": [[0, 141.0], [960, 138.4]], "time_sig": [[0, [4, 4]]]},
            "audio": {"bgm": {"filename": "song.mp3", "offset": 1074}},
            "note": {"bt": [[[0, 0]], [], [], []], "fx": [[], []], "laser": [[], []]}}


def test_preview_embeds_chart_and_audio(tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"ID3fake")
    page = build_preview(_chart(), audio)
    data = re.search(r'<script id="chart-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(data)["meta"]["title"] == "A </script> B"
    assert 'const AUDIO_SRC = "data:audio/mpeg;base64,SUQzZmFrZQ=="' in page
    assert "<title>A &lt;/script&gt; B</title>" in page


def test_preview_cli_finds_bgm_next_to_chart(tmp_path):
    chart = tmp_path / "chart.kson"
    chart.write_text(json.dumps(_chart()))
    (tmp_path / "song.mp3").write_bytes(b"ID3fake")
    out = tmp_path / "preview.html"
    assert main(["preview", str(chart), "-o", str(out)]) == 0
    assert "data:audio/mpeg;base64," in out.read_text()


def test_viewer_cli_without_chart(tmp_path):
    out = tmp_path / "viewer.html"
    assert main(["viewer", "-o", str(out)]) == 0
    page = out.read_text()
    data = re.search(r'<script id="chart-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    assert json.loads(data) is None
    assert 'id="files"' in page and 'multiple accept=".kson,.ksh' in page
    assert 'https://' not in page and 'http://' not in page
    assert "__CHART_JSON__" not in page and "__AUDIO_SRC__" not in page


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    return node


def _compare_ksh(paths):
    charts = [load_ksh(p) for p in paths]
    # Decode with the Python importer's UTF-8/CP932 policy, then compare the converters.
    texts = []
    for p in paths:
        try:
            texts.append(p.read_bytes().decode("utf-8-sig"))
        except UnicodeDecodeError:
            texts.append(p.read_bytes().decode("cp932"))
    code = """
const fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync('src/ksmauto/preview_template.html', 'utf8');
vm.runInThisContext(html.match(/<script id="ksh-converter">([\\s\\S]*?)<\\/script>/)[1]);
const texts = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(texts.map(parseKsh)));
"""
    result = subprocess.run([_node(), "-e", code], input=json.dumps(texts), cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    for path, actual, expected in zip(paths, json.loads(result.stdout), charts):
        assert actual == expected, str(path)


def test_browser_ksh_converter_fixtures():
    paths = sorted((Path(__file__).parent / "fixtures").rglob("*.ksh"))
    assert paths
    _compare_ksh(paths)


def test_browser_ksh_converter_corpus():
    paths = sorted((ROOT / "corpus").rglob("*.ksh"))
    if not paths:
        pytest.skip("local corpus is absent")
    _compare_ksh(paths)


def test_preview_js():
    node = _node()
    help_text = subprocess.run([node, "--help"], capture_output=True, text=True, timeout=10).stdout
    flags = ["--experimental-test-isolation=none"] if "--experimental-test-isolation" in help_text else []
    result = subprocess.run([node, "--test", *flags, "tests/preview.test.mjs"], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_viewer_browser(tmp_path):
    node = _node()
    available = subprocess.run([node, "-e", "require('playwright')"], cwd=ROOT, capture_output=True)
    if available.returncode:
        pytest.skip("node playwright is not installed")
    page = tmp_path / "viewer.html"
    page.write_text(build_preview(), encoding="utf-8")
    audio = tmp_path / "silent.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 8000 * 8)
    result = subprocess.run([node, "tests/preview-smoke.cjs", str(page), str(audio)], cwd=ROOT,
                            capture_output=True, text=True, timeout=60)
    if result.returncode == 77:
        pytest.skip("playwright Chromium is absent or cannot launch in this sandbox")
    assert result.returncode == 0, result.stdout + result.stderr


def test_browser_ksh_converter_options(tmp_path):
    header = "title=日本語\nartist=Test\nt=140\nm=song.ogg;fx.ogg\n"
    options = [
        "zoom_top=100\nzoom_top=200\nzoom_top_curve=0.3;0.7",
        "tilt=10\ntilt=normal\ntilt_curve=0.2;0.8",
        "tilt=big\nfiltertype=fx\nfiltertype=fx;bitc",
        "scroll_speed=-2\nscroll_speed=1.5\nscroll_speed_curve=0.5;0.1\nstop=48",
        "pfiltergain=40\npfiltergain=80\nchokkakuvol=25\nunknown=value=with=equals",
        "#define_fx custom type=Echo;waveLength=1/4;feedbackLevel=30%\nfx-l=custom;8;70\nfx:custom:waveLength=1/8",
        "#define_fx custom type=Gate;rate=70%;rate=50%\n#define_fx custom type=Echo\nfx-l=custom",
        "#define_filter custom type=PeakingFilter;freq=100Hz\nfiltertype=custom\nfilter:custom:freq=200Hz",
        "fx-l_se=clap;75\nchokkakuse=slam_swing\nlaserrange_l=2x\nlaser_l_curve=0.3;0.6",
        "//comment\\nsecond line\n;unknown-line\n__proto__=kept\nconstructor=kept",
    ]
    paths = []
    for ver in (100, 130, 160, 166, 167, 170, 200):
        for i, option in enumerate(options):
            text = (header + f"ver={ver}\n--\nbeat=7/8\n" + option +
                    "\n2000|12|C-@)192\n0000|S0|b-\n0000|00|--\n--\n"
                    "tilt=0.5\n0000|00|0-@<96\n0000|00|o-S>192;100;2;1\n0000|00|--\n--\n")
            path = tmp_path / f"{ver}-{i}.ksh"
            path.write_text(text, encoding="utf-8")
            paths.append(path)
    _compare_ksh(paths)


@pytest.mark.parametrize("auto,expected", [("", True), ("0", False), ("1", True)])
def test_browser_ksh_converter_slam_sounds(tmp_path, auto, expected):
    header = "title=Slam sounds\nt=120\nchokkakuvol=25\n"
    if auto:
        header += f"chokkakuautovol={auto}\n"
    rows = []
    names = ["up", "down", "swing", "mute", "custom.wav"]
    for i, name in enumerate(names):
        rows.extend([f"chokkakuse={name}", "0000|00|0-", "0000|00|o-", "0000|00|--"])
        if i == 0:
            rows.append("chokkakuvol=0")
        elif i == 1:
            rows.append("chokkakuvol=80")
    rows.extend(["0000|00|--"] * 17)  # 32 rows per measure: each pair is a slam
    path = tmp_path / "slams.ksh"
    path.write_text(header + "--\n" + "\n".join(rows) + "\n--\n", encoding="utf-8")
    assert load_ksh(path)["audio"]["key_sound"]["laser"] == {
        "legacy": {"vol_auto": expected}, "vol": [[0, 0.25], [90, 0], [180, 0.8]],
        "slam_event": {name: [i * 90] for i, name in enumerate(names)},
    }
    _compare_ksh([path])
