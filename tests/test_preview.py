import json
import re

from ksmauto.cli import main
from ksmauto.preview import build_preview


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
