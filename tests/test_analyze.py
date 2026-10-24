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


def test_stems_rows(tmp_path):
    """Synthetic stems: kick on beats, snare on 2 and 4, hats off-beat, a held vocal A4."""
    sr, bpm, offset, seconds = 22050, 150.0, 0.1, 24.0
    rng = np.random.default_rng(1)
    beat = 60.0 / bpm
    t = np.arange(int(0.08 * sr)) / sr
    kick = np.sin(2 * np.pi * 60 * t) * np.exp(-t * 40)
    snare = np.fft.rfft(rng.standard_normal(len(t)))
    snare[(np.fft.rfftfreq(len(t), 1 / sr) < 200) | (np.fft.rfftfreq(len(t), 1 / sr) > 5000)] = 0
    snare = np.fft.irfft(snare, len(t)) * np.exp(-t * 60)
    spectrum = np.fft.rfft(rng.standard_normal(len(t)))
    spectrum[np.fft.rfftfreq(len(t), 1 / sr) < 6000] = 0  # hi-hats live above ~6 kHz
    hat = np.fft.irfft(spectrum, len(t)) * np.exp(-t * 200)
    n = int(seconds * sr)
    drums, vocals = np.zeros(n), np.zeros(n)
    i = 0
    while offset + (i + 1) * beat < seconds - 0.1:
        s = int((offset + i * beat) * sr)
        drums[s:s + len(t)] += kick + (snare if i % 2 == 1 else 0)
        h = int((offset + (i + 0.5) * beat) * sr)
        drums[h:h + len(t)] += hat
        if i % 4 == 0:  # two beats of A4 at each measure start
            v = np.arange(int(2 * beat * sr)) / sr
            vocals[s:s + len(v)] += 0.3 * np.sin(2 * np.pi * 440 * v)
        i += 1
    stems = tmp_path / "stems"
    stems.mkdir()
    quiet = rng.standard_normal(n) * 1e-4
    for name, y in {"drums": drums, "vocals": vocals, "bass": quiet, "other": quiet}.items():
        sf.write(stems / f"{name}.wav", y, sr)
    sf.write(tmp_path / "mix.wav", (drums + vocals) / np.abs(drums + vocals).max() * 0.8, sr)

    a = analyze(tmp_path / "mix.wav", offset_ms=100, stems=stems)  # pin the downbeat
    m = a["measures"][4]["stems"]
    beats_of = {row: [b for b, h in m["onsets"][row] if h >= 0.3] for row in ("kick", "snare", "hat")}
    assert beats_of["kick"] == [0, 1, 2, 3]
    assert beats_of["snare"] == [1, 3]
    assert beats_of["hat"] == [0.5, 1.5, 2.5, 3.5]
    (start, length), = m["sustain"]["vocal"]
    assert start == 0 and 1.5 <= length <= 2
    assert all(abs(p - 69) < 0.5 for _, p in m["vocal_pitch"])
    assert not m["onsets"]["bass"] and not m["sustain"]["bass"]  # near-silent stem
    text = to_text(a)
    assert "vpitch" in text and "kick" in text


def test_stem_cells_short_stem_and_triplet_rows():
    from ksmauto.analyze import STEM_ROWS, _measure_stems, _pitch_row, _span_row

    # The stem ends ~58 ms into a 125 ms cell: the cell is mostly silent.
    frames = 10
    tracks = {"peaks": {k: (np.array([]), np.array([])) for k in STEM_ROWS},
              "active": {"bass": np.ones(frames, dtype=bool)}, "pitch": np.full(frames, 69.0)}
    m = _measure_stems(tracks, 0.0, 2.0, 4)
    assert m["sustain"]["bass"] == [] and m["vocal_pitch"] == []

    # Triplet display: pitch and sustain agree on which cells are voiced.
    span = _span_row("." * 12, [[0.25, 0.25]], 4, 3)
    pitch = _pitch_row([[0.25, 69.0]], 4, 3, 60.0, 72.0)
    assert [c == "=" for c in span] == [c != "." for c in pitch]
