import json
import re
import shutil
import subprocess
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
const html = fs.readFileSync('src/ksmauto/viewer.html', 'utf8');
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
