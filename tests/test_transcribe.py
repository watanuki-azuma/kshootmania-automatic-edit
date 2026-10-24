import json
import subprocess

import pytest

from ksmauto.transcribe import _write_muscriptor_notes, transcribe_muscriptor


def _events(*notes):
    """MuScriptor --format json events for (start, end, pitch, instrument) notes."""
    out = []
    for i, (start, end, pitch, instrument) in enumerate(notes):
        out.append({"type": "start", "pitch": pitch, "start_time": start, "index": i, "instrument": instrument})
        out.append({"type": "end", "end_time": end, "start_event_index": i})
    return out


def test_muscriptor_notes_rows(tmp_path):
    events = _events((2.123456, 2.987654, 64, "acoustic_piano"), (1, 2, 60, "electric_piano"),
                     (0, 1, 50, "acoustic_guitar"), (1, 2, 52, "distorted_electric_guitar"),
                     (0, 1, 40, "electric_bass"), (0.5, 1, 67, "voice"),
                     (0, 0.5, 72, "synth_lead"), (1, 1.5, 72, "synth_pad"), (0, 0.1, 36, "drums"))
    events.append({"type": "start", "pitch": 61, "start_time": 3, "index": 99, "instrument": "acoustic_piano"})
    out = tmp_path / "stems"
    paths = _write_muscriptor_notes(events, out)
    assert [p.name for p in paths] == ["bass.notes.json", "guitar.notes.json", "other.notes.json",
                                       "piano.notes.json", "vocal.notes.json"]
    rows = {p.name.split(".")[0]: json.loads(p.read_text()) for p in paths}
    assert rows["piano"] == [[1, 2, 60, 1.0], [2.1235, 2.9877, 64, 1.0]]  # the unended note is dropped
    assert rows["guitar"] == [[0, 1, 50, 1.0], [1, 2, 52, 1.0]]
    assert rows["bass"] == [[0, 1, 40, 1.0]]
    assert rows["vocal"] == [[0.5, 1, 67, 1.0]]
    assert rows["other"] == [[0, 0.5, 72, 1.0], [1, 1.5, 72, 1.0]]


def test_muscriptor_drums_only(tmp_path):
    assert _write_muscriptor_notes(_events((0, 0.1, 36, "drums")), tmp_path) == []
    assert not list(tmp_path.glob("*.notes.json"))


def test_muscriptor_failure_does_not_write_notes(tmp_path, monkeypatch):
    def fail(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("ksmauto.transcribe.subprocess.run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        transcribe_muscriptor(tmp_path / "mix.wav", tmp_path / "stems")
    assert not (tmp_path / "stems").exists()
