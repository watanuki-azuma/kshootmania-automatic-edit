import numpy as np
import pytest

sf = pytest.importorskip("soundfile")
from ksmauto.analyze import analyze, to_text  # noqa: E402


def _click_track(path, bpm, offset_sec, seconds=40.0, sr=22050):
    """Kick on every beat, accented snare-ish noise on beats 2 and 4, hats on off-beats."""
    rng = np.random.default_rng(0)
    y = np.zeros(int(seconds * sr))
    beat = 60.0 / bpm
    t = np.arange(int(0.08 * sr)) / sr
    kick = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 40)
    snare = rng.standard_normal(len(t)) * np.exp(-t * 60) * 0.5
    hat = np.diff(rng.standard_normal(len(t) + 1)) * np.exp(-t * 200) * 0.2
    i = 0
    while offset_sec + i * beat < seconds - 0.1:
        s = int((offset_sec + i * beat) * sr)
        y[s:s + len(t)] += kick
        if i % 2 == 1:
            y[s:s + len(t)] += snare
        h = int((offset_sec + (i + 0.5) * beat) * sr)
        y[h:h + len(t)] += hat[: len(y[h:h + len(t)])]
        i += 1
    sf.write(path, y / np.abs(y).max() * 0.8, sr)


@pytest.mark.parametrize("bpm,offset", [(150.0, 0.1), (182.0, 0.25)])
def test_click_track_tempo_and_offset(tmp_path, bpm, offset):
    p = tmp_path / "click.wav"
    _click_track(p, bpm, offset)
    a = analyze(p)
    assert abs(a["tempo"]["bpm"] - bpm) <= 0.5
    beat_ms = 60000.0 / bpm
    err = (a["offset_ms"] - offset * 1000) % beat_ms
    # Synthetic clicks have instantaneous attacks and read ~20 ms earlier than music.
    assert min(err, beat_ms - err) <= 30
    assert a["measures"] and a["sections"]
    assert to_text(a).startswith(f"BPM {bpm:g}")
