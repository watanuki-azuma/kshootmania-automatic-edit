import json
import sys
from pathlib import Path

import pytest

from ksmauto.cli import main
from ksmauto.kson import load_kson


GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"


def test_convert_validate_info(tmp_path, capsys):
    output = tmp_path / "gram.kson"
    assert main(["convert", str(GRAM), "-o", str(output)]) == 0
    assert load_kson(output)["meta"]["title"] == "Gram"
    assert main(["validate", str(output), str(GRAM)]) == 0
    assert main(["info", str(output), str(GRAM)]) == 0
    text = capsys.readouterr().out
    assert "Gram / Blast Smith" in text and "Level: 16" in text
    assert "BPM: 191" in text and "Duration:" in text
    assert "Laser: 89 sections, 145 slams" in text


def test_default_convert_output(tmp_path):
    path = tmp_path / "chart.ksh"
    path.write_text("title=Test\nt=120\n--\n0000|00|--\n--\n")
    assert main(["convert", str(path)]) == 0
    assert path.with_suffix(".kson").exists()


def test_validate_errors_and_missing_file(tmp_path, capsys):
    path = tmp_path / "broken.kson"
    path.write_text('{"format_version":1}')
    assert main(["validate", str(path)]) == 1
    assert "error: $.meta" in capsys.readouterr().out
    assert main(["info", str(path)]) == 1
    assert main(["convert", str(tmp_path / "missing.ksh")]) == 1
    assert main(["validate", str(tmp_path / "missing.kson")]) == 1


def test_transcribe_default_bytedance(tmp_path, monkeypatch, capsys):
    from ksmauto.transcribe import _SCRIPT

    audio = tmp_path / "piano.wav"

    def run(cmd, check):
        assert check and cmd[:3] == [sys.executable, "-c", _SCRIPT]
        assert cmd[3:5] == [str(audio), str(audio.with_suffix(".notes.json"))]
        Path(cmd[4]).write_text("[[0.0, 1.0, 60, 0.8]]")

    monkeypatch.setattr("ksmauto.transcribe.subprocess.run", run)
    assert main(["transcribe", str(audio), "--python", sys.executable]) == 0
    assert capsys.readouterr().out == f"1 notes: {audio.with_suffix('.notes.json')}\n"


@pytest.mark.parametrize("model", [None, "medium"])
def test_transcribe_muscriptor(tmp_path, monkeypatch, capsys, model):
    audio = tmp_path / "mix.wav"
    out = tmp_path / "stems" if model else tmp_path
    python = "/models/python" if model else sys.executable

    def run(cmd, check):
        assert check
        assert cmd[:9] == [python, "-m", "muscriptor", "transcribe", "--model", model or "small",
                           "--format", "json", str(audio)]
        assert cmd[9] == "-o"
        Path(cmd[10]).write_text(json.dumps([
            {"type": "start", "pitch": 60, "start_time": 1, "index": 0, "instrument": "acoustic_piano"},
            {"type": "start", "pitch": 72, "start_time": 0, "index": 1, "instrument": "synth_lead"},
            {"type": "end", "end_time": 1, "start_event_index": 1},
            {"type": "end", "end_time": 2, "start_event_index": 0}]))

    monkeypatch.setattr("ksmauto.transcribe.subprocess.run", run)
    monkeypatch.setattr("ksmauto.transcribe.importlib.util.find_spec", lambda name: object())
    args = ["transcribe", str(audio), "--engine", "muscriptor"]
    if model:
        args += ["--model", model, "--python", python, "-o", str(out)]
    assert main(args) == 0
    assert json.loads((out / "piano.notes.json").read_text()) == [[1, 2, 60, 1.0]]
    assert json.loads((out / "other.notes.json").read_text()) == [[0, 1, 72, 1.0]]
    assert capsys.readouterr().out.splitlines() == [f"1 notes: {out / 'other.notes.json'}",
                                                 f"1 notes: {out / 'piano.notes.json'}"]


@pytest.mark.parametrize("engine,package", [("bytedance", "piano_transcription_inference"), ("muscriptor", "muscriptor")])
def test_transcribe_missing_engine(monkeypatch, capsys, engine, package):
    def find_spec(name):
        assert name == package
        return None

    monkeypatch.setattr("ksmauto.transcribe.importlib.util.find_spec", find_spec)
    assert main(["transcribe", "mix.wav", "--engine", engine]) == 1
    assert f"{package} is not installed" in capsys.readouterr().err
