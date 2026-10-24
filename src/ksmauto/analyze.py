"""Audio analysis for chart authoring (see docs/analysis-format.md).

Requires the `audio` extra (numpy, scipy, librosa, soundfile).
"""

from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from scipy.signal import find_peaks

SR = 22050
HOP = 128  # ~5.8 ms per frame
N_FFT = 1024  # short window keeps onset timing tight
BANDS = {"low": (20.0, 180.0), "mid": (180.0, 3000.0), "high": (5000.0, 11000.0)}
# Stem rows for `--stems` (see ksmauto.separate): row -> (stem file, band in Hz).
# The drum rows come from an NMF split of the drum stem (DRUM_TEMPLATES), not a band.
STEM_ROWS = {"kick": ("drums", None, None), "snare": ("drums", None, None), "hat": ("drums", None, None),
             "bass": ("bass", 20.0, 2000.0), "vocal": ("vocals", 80.0, 8000.0), "other": ("other", 20.0, 11000.0)}
# Initial spectra (centre Hz, width in octaves) and the Hz range each may learn. Kick
# energy above a few hundred Hz otherwise ends up in the snare, so the snare and hi-hat
# templates are kept out of the kick's body and the kick takes its own click.
DRUM_TEMPLATES = {"kick": (70.0, 0.6, 0.0, 5000.0), "snare": (1200.0, 1.4, 500.0, 5000.0),
                  "hat": (9000.0, 0.5, 5000.0, SR / 2)}
# Rows that also report where the stem keeps sounding, as [start beat, length] spans.
SUSTAIN_ROWS = {"bass": "bass", "vocal": "vocals", "other": "other"}
# Pitched rows with a lane column (text column name). `piano` exists when the stem
# directory has piano.wav (`separate --model htdemucs_6s`).
LANE_ROWS = {"other": "olane", "piano": "plane"}
# Notes from `ksmauto transcribe` closer than this start one chord.
CHORD_SEC = 0.035
# A stem counts as sounding within ACTIVE_DB of its own loud level (95th percentile),
# and never below FLOOR_DB under the loudest stem (a near-silent stem is all bleed).
ACTIVE_DB = 20.0
FLOOR_DB = 40.0
# Pitch range (lowest note, semitones) of the `other` stem's note onsets.
OTHER_PITCH = ("C2", 72)
BPM_RANGE = (60.0, 300.0)
# Prior for octave resolution: rhythm games mostly sit in this range.
BPM_PREFERRED = (120.0, 240.0)
# Spectral-flux peaks land slightly before the perceived attack; calibrated on the
# official corpus (tests/eval/eval_analyze.py).
LATENCY_SEC = 0.006


def _band_flux(S: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    band = S[(freqs >= lo) & (freqs < hi)]
    logb = np.log1p(100.0 * band)
    flux = np.maximum(0.0, np.diff(logb, axis=1, prepend=logb[:, :1])).sum(axis=0)
    flux = flux - uniform_filter1d(flux, 64)
    flux = np.maximum(flux, 0.0)
    peak = np.percentile(flux, 99.5)
    return flux / peak if peak > 0 else flux


def _note_flux(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Onset envelope and per-semitone attack strength from a constant-Q spectrum.

    Each semitone is compared with its own recent past, so a new piano note shows up
    even under a held pad, which a broadband flux misses.
    """
    fmin, bins = librosa.note_to_midi(OTHER_PITCH[0]), OTHER_PITCH[1]
    # Half-length filters: low notes still rise within a few frames.
    C = np.abs(librosa.cqt(y, sr=SR, hop_length=HOP, fmin=librosa.midi_to_hz(fmin),
                           n_bins=bins * 3, bins_per_octave=36, filter_scale=0.5))
    logc = np.log1p(100.0 * C / (C.max() + 1e-9))
    # Compare with half a filter length back (low notes rise slowly) and +-1/3 semitone,
    # so vibrato and slow swells do not count as attacks.
    wide = maximum_filter1d(logc, 3, axis=0)
    hz = librosa.cqt_frequencies(bins * 3, fmin=librosa.midi_to_hz(fmin), bins_per_octave=36)
    lags = np.clip(np.round(0.5 / (2 ** (1 / 36) - 1) * SR / hz / 2 / HOP), 3, 24).astype(int)
    rise = np.zeros_like(logc)
    for lag in np.unique(lags):
        rows = lags == lag
        rise[rows, lag:] = np.maximum(0.0, logc[rows, lag:] - wide[rows, :-lag])
    rise = np.vstack([rise[-1:] * 0, rise[:-1]]).reshape(bins, 3, -1).max(axis=1)  # semitone = its bin +-1
    env = rise.sum(axis=0)
    env = np.maximum(env - uniform_filter1d(env, 64), 0.0)
    peak = np.percentile(env, 99.5)
    return (env / peak if peak > 0 else env), rise


def _top_note(rise: np.ndarray, frame: int) -> int:
    """Row of the highest note starting at `frame` (the melody over the chord).

    Rows are harmonic-summed so a note's fundamental outscores its own overtones; among
    the clear peaks of that sum, the highest one wins.
    """
    w = rise[:, frame:frame + 12].sum(axis=1)
    s = w.copy()
    for h, weight in ((2, 0.5), (3, 0.33), (4, 0.25)):
        k = int(round(12 * np.log2(h)))
        s[:-k] += weight * w[k:]
    edged = np.pad(s, 1, constant_values=-np.inf)
    peaks = (s >= 0.6 * s.max()) & (s >= edged[:-2]) & (s >= edged[2:])
    return int(np.flatnonzero(peaks)[-1])


def _notes_track(notes: list, frames: int) -> tuple:
    """Onsets (chords merged), their top note and sounding frames from transcribed notes."""
    fps = SR / HOP
    notes = sorted(notes)
    groups = []
    for onset, offset, midi, velocity in notes:
        # An octave over a note that sounds at that moment is a doubling (or an overtone the
        # model took for a note); the lower one carries the melody.
        if any(m == midi - 12 and on - CHORD_SEC < onset < off for on, off, m, _ in notes):
            midi = midi - 12
        if groups and onset - groups[-1][0] < CHORD_SEC:
            groups[-1][1] = max(groups[-1][1], velocity)
            groups[-1][2] = max(groups[-1][2], midi)
        else:
            groups.append([onset, velocity, midi])
    loud = np.percentile([g[1] for g in groups], 90) if groups else 1.0
    active = np.zeros(frames, dtype=bool)
    for onset, offset, _, _ in notes:
        active[int(onset * fps):int(offset * fps) + 1] = True
    times = np.array([g[0] for g in groups])
    return (times, np.clip([g[1] / loud for g in groups], 0, 1)), np.array([float(g[2]) for g in groups]), active


def _comb_score(env: np.ndarray, period: float, phase: float) -> float:
    n = int((len(env) - 1 - phase) / period)
    if n < 8:
        return 0.0
    idx = phase + period * np.arange(n + 1)
    lo = np.floor(idx).astype(int)
    frac = idx - lo
    hi = np.minimum(lo + 1, len(env) - 1)
    return float(np.mean(env[lo] * (1 - frac) + env[hi] * frac))


def _best_phase(env: np.ndarray, period: float, steps: int = 96) -> tuple[float, float]:
    phases = np.linspace(0.0, period, steps, endpoint=False)
    scores = [_comb_score(env, period, p) for p in phases]
    i = int(np.argmax(scores))
    return float(phases[i]), float(scores[i])


def _estimate_tempo(env: np.ndarray, fps: float) -> tuple[float, float, list[list[float]]]:
    """Coarse tempo via autocorrelation, refined by comb search over the whole song."""
    ac = librosa.autocorrelate(env - env.mean(), max_size=int(fps * 60.0 / BPM_RANGE[0]) + 2)
    lags = np.arange(len(ac))
    valid = (lags >= fps * 60.0 / BPM_RANGE[1]) & (lags <= fps * 60.0 / BPM_RANGE[0])
    peaks, _ = find_peaks(np.where(valid, ac, 0.0))
    peaks = sorted(peaks, key=lambda p: ac[p], reverse=True)[:8]
    cands: dict[float, float] = {}
    for p in peaks:
        bpm = 60.0 * fps / p
        for mult in (0.5, 1.0, 2.0, 2.0 / 3.0, 1.5):
            b = bpm * mult
            if BPM_RANGE[0] <= b <= BPM_RANGE[1]:
                cands[round(b, 1)] = 0.0
    scored = []
    for b in cands:
        best = _refine_bpm(env, fps, b, span=1.5, step=0.05)
        scored.append(best)
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[0][1]
    # Slower metrical levels (half bar, 2/5 ...) often fit the comb best; take the
    # best fit inside the preferred range unless it is clearly worse.
    pref = [s for s in scored if _preferred(s[0]) and s[1] >= 0.6 * top]
    chosen = pref[0] if pref else scored[0]
    bpm, score = _refine_bpm(env, fps, chosen[0], span=0.2, step=0.005)
    bpm = _snap_bpm(env, fps, bpm, score)
    uniq: list[list[float]] = []
    for b, s in scored:
        if all(abs(b - u[0]) > 0.5 for u in uniq):
            uniq.append([round(b, 2), round(s / top, 3)])
    conf = 1.0 if len(scored) < 2 else float(np.clip(1.0 - _second_distinct(scored, chosen[0]) / top, 0.0, 1.0)) * 0.5 + 0.5
    return bpm, conf, uniq[:5]


def _preferred(bpm: float) -> bool:
    return BPM_PREFERRED[0] <= bpm < BPM_PREFERRED[1]


def _second_distinct(scored: list[tuple[float, float]], bpm: float) -> float:
    for b, s in scored:
        ratio = b / bpm
        if min(abs(ratio - r) for r in (0.5, 1.0, 2.0)) > 0.02:
            return s
    return 0.0


def _refine_bpm(env: np.ndarray, fps: float, bpm: float, span: float, step: float) -> tuple[float, float]:
    best = (bpm, -1.0)
    for b in np.arange(bpm - span, bpm + span + 1e-9, step):
        _, s = _best_phase(env, 60.0 * fps / b, steps=48)
        if s > best[1]:
            best = (float(b), s)
    return best


def _snap_bpm(env: np.ndarray, fps: float, bpm: float, score: float) -> float:
    """Charts use round BPMs; snap when the round value fits nearly as well."""
    for grid in (1.0, 0.5):
        r = round(bpm / grid) * grid
        if abs(r - bpm) <= 0.15:
            _, s = _best_phase(env, 60.0 * fps / r, steps=96)
            if s >= 0.9 * score:
                return float(r)
    return round(bpm, 2)


def _downbeat_phase(features, phase, period, beats_per_measure) -> int:
    n_frames = features[0].shape[1]
    edges = (phase + period * np.arange(int((n_frames - phase) / period) + 1)).astype(int)
    if len(edges) < 4 * beats_per_measure:
        return 0
    total = np.zeros(beats_per_measure)
    for feat in features:
        beats = np.stack([feat[:, a:b].mean(axis=1) for a, b in zip(edges[:-1], edges[1:])], axis=1)
        z = (beats - beats.mean(axis=1, keepdims=True)) / (beats.std(axis=1, keepdims=True) + 1e-9)
        idx = np.arange(2, z.shape[1] - 2)
        nov = np.array([np.linalg.norm(z[:, i - 2:i].mean(axis=1) - z[:, i:i + 2].mean(axis=1)) for i in idx])
        score = np.array([nov[idx % beats_per_measure == k].mean() for k in range(beats_per_measure)])
        total += score / score.mean()
    return int(np.argmax(total))


def _quantize(t_beats: np.ndarray, tol: float = 0.09) -> list[float | None]:
    """Snap beat positions to 1/4 or 1/3 beat; None when far from both."""
    out: list[float | None] = []
    for t in t_beats:
        q4 = round(t * 4) / 4
        q3 = round(t * 3) / 3
        e4, e3 = abs(t - q4), abs(t - q3)
        if e4 <= e3 and e4 <= tol:
            out.append(q4)
        elif e3 < e4 and e3 <= tol:
            out.append(q3)
        else:
            out.append(None)
    return out


def _sections(feat: np.ndarray, n_measures: int) -> list[dict]:
    """Novelty-based segmentation on per-measure features, boundaries on 4-measure units."""
    if n_measures < 8:
        return [{"start": 0, "end": n_measures, "label": "A"}]
    f = (feat - feat.mean(axis=0)) / (feat.std(axis=0) + 1e-9)
    f = f / (np.linalg.norm(f, axis=1, keepdims=True) + 1e-9)
    ssm = f @ f.T
    k = 4
    nov = np.zeros(n_measures)
    for i in range(k, n_measures - k + 1):
        a, b = ssm[i - k:i, i - k:i], ssm[i:i + k, i:i + k]
        c = ssm[i - k:i, i:i + k]
        nov[i] = a.mean() + b.mean() - 2 * c.mean()
    bounds = [0]
    cand = [i for i in range(4, n_measures - 3, 4)]
    thr = np.percentile(nov[cand], 60) if cand else 0
    for i in cand:
        if nov[i] >= thr and nov[i] >= nov[max(0, i - 4)] and nov[i] >= nov[min(n_measures - 1, i + 4)]:
            bounds.append(i)
    bounds.append(n_measures)
    segs = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    means = [f[s:e].mean(axis=0) for s, e in segs]
    labels: list[str] = []
    protos: list[np.ndarray] = []
    for m in means:
        m = m / (np.linalg.norm(m) + 1e-9)
        sims = [float(m @ p) for p in protos]
        if sims and max(sims) > 0.8:
            labels.append(chr(ord("A") + int(np.argmax(sims))))
        else:
            protos.append(m)
            labels.append(chr(ord("A") + len(protos) - 1))
    return [{"start": s, "end": e, "label": lab} for (s, e), lab in zip(segs, labels)]


def analyze(path: str | Path, beats_per_measure: int = 4, tempo: list[list[float]] | None = None,
            offset_ms: int | None = None, stems: str | Path | None = None) -> dict:
    """`tempo` ([[measure, bpm], ...]) and `offset_ms` override the estimates, for
    songs whose tempo changes (the estimator assumes one constant tempo).
    `stems` is a directory from `ksmauto separate`; tempo and offset still come
    from the mix, and each measure gains per-instrument rows."""
    path = Path(path)
    y, sr = librosa.load(path, sr=SR, mono=True)
    duration = len(y) / sr
    fps = sr / HOP
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    bands = {name: _band_flux(S, freqs, lo, hi) for name, (lo, hi) in BANDS.items()}
    env_all = _band_flux(S, freqs, 20.0, 11000.0)
    # Percussive-leaning envelope for tempo/phase: kick + snare + hats.
    env = bands["low"] + 0.6 * bands["mid"] + 0.4 * bands["high"] + env_all

    if tempo:
        tempo = sorted([int(m), float(b)] for m, b in tempo)
        bpm, conf, cands = tempo[0][1], 1.0, [[tempo[0][1], 1.0]]
    else:
        bpm, conf, cands = _estimate_tempo(env, fps)
        tempo = [[0, bpm]]
    period = 60.0 * fps / bpm
    phase, _ = _best_phase(env, period, steps=192)
    # The comb also locks onto off-beats (hats, off-beat bass). Off-beat bass is
    # common in this genre, so the mid band (snare, vocals) decides.
    off = (phase + period / 2) % period
    if _comb_score(bands["mid"], period, off) > _comb_score(bands["mid"], period, phase):
        phase = off

    # Downbeat: harmony and timbre change most across bar lines, so pick the beat
    # phase whose boundaries show the largest chroma/MFCC novelty.
    measure_frames = period * beats_per_measure
    chroma = librosa.feature.chroma_stft(S=S**2, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(librosa.feature.melspectrogram(S=S**2, sr=sr)), n_mfcc=13)
    best_db = _downbeat_phase([chroma, mfcc], phase, period, beats_per_measure)
    first_downbeat = (phase + best_db * period) % measure_frames
    offset_sec = (first_downbeat / fps + LATENCY_SEC) % (period * beats_per_measure / fps)
    if offset_ms is not None:
        offset_sec = offset_ms / 1000.0
    starts = [offset_sec]
    while starts[-1] < duration:
        m = len(starts) - 1
        b = [v for at, v in tempo if at <= m][-1]
        starts.append(starts[-1] + 60.0 / b * beats_per_measure)
    n_measures = len(starts) - 1

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]

    peaks = {name: _peaks(e, fps, period) for name, e in list(bands.items()) + [("all", env_all)]}
    tracks = _stem_tracks(Path(stems), period) if stems else None

    measures = []
    feats = []
    for m in range(n_measures):
        t0 = starts[m]
        measure_sec = starts[m + 1] - t0
        f0, f1 = int(t0 * fps), int((t0 + measure_sec) * fps)
        seg = slice(max(0, f0), max(f0 + 1, min(f1, len(rms))))
        onsets = {name: _measure_onsets(times, heights, t0, measure_sec, beats_per_measure)
                  for name, (times, heights) in peaks.items()}
        measures.append({
            "index": m,
            "start_sec": round(t0, 4),
            "energy": float(rms[seg].mean()) if f0 < len(rms) else 0.0,
            "onsets": onsets,
        })
        if tracks:
            measures[-1]["stems"] = _measure_stems(tracks, t0, measure_sec, beats_per_measure)
        feats.append(np.concatenate([chroma[:, seg].mean(axis=1), mfcc[:, seg].mean(axis=1)]))

    emax = max((m["energy"] for m in measures), default=1.0) or 1.0
    for m in measures:
        m["energy"] = round(m["energy"] / emax, 3)
    sections = _sections(np.array(feats), n_measures)
    for s in sections:
        s["energy"] = round(float(np.mean([measures[i]["energy"] for i in range(s["start"], s["end"])])), 3)

    return {
        "version": 0,
        "audio": {"path": path.name, "duration_sec": round(duration, 3), "sample_rate": int(sr)},
        "tempo": {
            "bpm": bpm,
            "confidence": round(conf, 3),
            "candidates": cands,
            "changes": [[m, b] for m, b in tempo[1:]],
            "time_sig": [beats_per_measure, 4],
        },
        "offset_ms": int(round(offset_sec * 1000)),
        "measures": measures,
        "sections": sections,
    }


def _peaks(e: np.ndarray, fps: float, period: float) -> tuple[np.ndarray, np.ndarray]:
    idx, props = find_peaks(e, height=0.12, distance=max(1, int(period / 4 * 0.6)))
    return idx / fps, np.clip(props["peak_heights"], 0, 1)


def _measure_onsets(times, heights, t0: float, measure_sec: float, beats_per_measure: int) -> list:
    beat_sec = measure_sec / beats_per_measure
    sel = (times >= t0 - beat_sec * 0.1) & (times < t0 + measure_sec - beat_sec * 0.1)
    best: dict[float, float] = {}
    for qb, h in zip(_quantize((times[sel] - t0) / beat_sec), heights[sel]):
        if qb is None or qb < 0 or qb >= beats_per_measure:
            continue
        key = round(qb, 4)
        best[key] = max(best.get(key, 0.0), float(h))
    return [[_fmt_beat(b), round(h, 2)] for b, h in sorted(best.items())]


def _drum_flux(y: np.ndarray) -> dict[str, np.ndarray]:
    """Onset envelopes for kick / snare / hi-hat from NMF with masked, adaptive templates."""
    M = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=N_FFT, hop_length=HOP, n_mels=64,
                                       fmax=SR / 2, power=1.0)
    mf = librosa.mel_frequencies(n_mels=66, fmax=SR / 2)[1:-1]  # filter centres (edges excluded)
    logf = np.log2(mf + 1)
    W = np.stack([np.exp(-0.5 * ((logf - np.log2(hz)) / width) ** 2) for hz, width, _, _ in DRUM_TEMPLATES.values()],
                 axis=1) + 1e-3
    mask = np.stack([((mf >= low) & (mf <= high)).astype(float) for _, _, low, high in DRUM_TEMPLATES.values()],
                    axis=1)
    W = W * mask / (W * mask).sum(axis=0)
    H = np.full((W.shape[1], M.shape[1]), M.mean())
    eps = 1e-9
    for it in range(80):  # KL multiplicative updates; templates adapt after a warm-up
        H *= (W.T @ (M / (W @ H + eps))) / (W.sum(axis=0)[:, None] + eps)
        if it >= 10:
            W *= ((M / (W @ H + eps)) @ H.T) / (H.sum(axis=1)[None, :] + eps) * mask
            W /= W.sum(axis=0)
    logh = np.log1p(50.0 * H / (H.max() + eps))
    flux = np.maximum(0.0, np.diff(logh, axis=1, prepend=logh[:, :1]))
    flux = np.maximum(flux - uniform_filter1d(flux, 64, axis=1), 0.0)
    # A sharp attack splashes into every template; keep a row's onset only if no other
    # drum starts at least twice as strongly at the same moment.
    # Compare linear attacks, each scaled by the row's own strong attacks: the log scale
    # inflates faint leakage, and raw units would let the kick hide a snare on the beat.
    rise = np.maximum(0.0, np.diff(H, axis=1, prepend=H[:, :1]))
    rise /= np.percentile(rise, 99.5, axis=1, keepdims=True) + eps
    local = maximum_filter1d(rise, 5, axis=1)
    out = {}
    for k, name in enumerate(DRUM_TEMPLATES):
        row = np.where(local[k] * 2 >= np.delete(local, k, axis=0).max(axis=0), flux[k], 0.0)
        peak = np.percentile(row, 99.5)
        out[name] = row / peak if peak > 0 else row
    return out


def _stem_tracks(stems_dir: Path, period: float) -> dict:
    """Onset peaks per stem row, sounding frames per sustained stem, and vocal pitch."""
    fps = SR / HOP
    rows = dict(STEM_ROWS)
    if (stems_dir / "piano.wav").exists():
        rows["piano"] = ("piano", None, None)
    loaded, levels = {}, {}
    for stem in {stem for stem, _, _ in rows.values()}:
        y, _ = librosa.load(stems_dir / f"{stem}.wav", sr=SR, mono=True)
        levels[stem] = librosa.amplitude_to_db(librosa.feature.rms(y=y, hop_length=HOP)[0], ref=1.0)
        loaded[stem] = (y, np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)))
    floor = max(np.percentile(db, 95) for db in levels.values()) - FLOOR_DB
    for stem, db in levels.items():
        loaded[stem] += (db > max(np.percentile(db, 95) - ACTIVE_DB, floor),)
    freqs = librosa.fft_frequencies(sr=SR, n_fft=N_FFT)
    active = {row: loaded[stem][2] for row, stem in {**SUSTAIN_ROWS, **{r: r for r in LANE_ROWS if r in rows}}.items()}
    # Voicing decides where the vocal sounds; the level gate drops bleed from other stems.
    f0, voiced, _ = librosa.pyin(loaded["vocals"][0], fmin=80.0, fmax=1000.0, sr=SR,
                                 frame_length=1024, hop_length=HOP)
    n = min(len(voiced), len(active["vocal"]))
    active["vocal"] = active["vocal"][:n] & voiced[:n]
    pitch = np.where(active["vocal"], librosa.hz_to_midi(f0[:n]), np.nan)
    envs = _drum_flux(loaded["drums"][0])
    # Pitched stems are polyphonic: without a transcription, onsets and pitch come from
    # the note that starts (the piano/synth contour), not a transcribed melody.
    attacks, peaks, lane_pitch = {}, {}, {}
    for row in LANE_ROWS:
        notes_path = stems_dir / f"{row}.notes.json"
        if row in rows and notes_path.exists():
            peaks[row], pitches, active[row] = _notes_track(json.loads(notes_path.read_text()), len(active[row]))
            lane_pitch[row] = (peaks[row][0], pitches)
        elif row in rows:
            envs[row], attacks[row] = _note_flux(loaded[row][0])
    for row, (stem, lo, hi) in rows.items():
        if row in peaks:
            continue
        env = envs[row] if row in envs else _band_flux(loaded[stem][1], freqs, lo, hi)
        times, heights = _peaks(env, fps, period)
        if row in active:  # drop onsets where the stem itself is quiet
            frames = np.minimum((times * fps).astype(int), len(active[row]) - 1)
            keep = active[row][frames]
            times, heights = times[keep], heights[keep]
        peaks[row] = (times, heights)
    fmin = librosa.note_to_midi(OTHER_PITCH[0])
    for row, attack in attacks.items():
        times = peaks[row][0]
        frames = np.minimum((times * fps).astype(int), attack.shape[1] - 1)
        lane_pitch[row] = (times, np.array([fmin + _top_note(attack, i) for i in frames], dtype=float))
    return {"peaks": {row: peaks[row] for row in rows}, "active": active, "pitch": pitch, "lane_pitch": lane_pitch}


def _measure_stems(tracks: dict, t0: float, measure_sec: float, beats_per_measure: int) -> dict:
    fps = SR / HOP
    cells = beats_per_measure * 4
    cell_sec = measure_sec / cells
    out = {"onsets": {row: _measure_onsets(*peaks, t0, measure_sec, beats_per_measure)
                      for row, peaks in tracks["peaks"].items()},
           "sustain": {}, "vocal_pitch": [],
           **{f"{row}_pitch": _measure_onsets(*pitch, t0, measure_sec, beats_per_measure)
              for row, pitch in tracks["lane_pitch"].items()}}
    bounds = [(int((t0 + k * cell_sec) * fps), int((t0 + (k + 1) * cell_sec) * fps)) for k in range(cells)]
    # Frames past the end of a stem count as silent, so a cell is judged on its full length.
    for row, frames in tracks["active"].items():
        spans = []
        for k, (a, b) in enumerate(bounds):
            if b > a and frames[max(0, a):max(0, b)].sum() >= 0.5 * (b - a):
                if spans and spans[-1][0] + spans[-1][1] == k:
                    spans[-1][1] += 1
                else:
                    spans.append([k, 1])
        out["sustain"][row] = [[_fmt_beat(k / 4), _fmt_beat(n / 4)] for k, n in spans]
    for k, (a, b) in enumerate(bounds):
        seg = tracks["pitch"][max(0, a):max(0, b)]
        if b > a and np.isfinite(seg).sum() >= 0.5 * (b - a):
            out["vocal_pitch"].append([_fmt_beat(k / 4), round(float(np.nanmedian(seg)), 1)])
    return out


def _fmt_beat(b: float) -> float:
    return round(b, 4)


def _grid_row(onsets: list, beats: int, div: int) -> str:
    cells = ["."] * (beats * div)
    for b, h in onsets:
        i = int(round(b * div))
        if 0 <= i < len(cells) and abs(b * div - i) < 1e-3:
            c = "X" if h >= 0.6 else ("x" if h >= 0.3 else ".")
            if c != "." and (cells[i] == "." or c == "X"):
                cells[i] = c
    return "".join(cells)


def _span_row(row: str, spans: list, beats: int, div: int) -> str:
    """Overlay sustain spans ('=') under the onset marks of a stem row."""
    cells = list(row)
    for start, length in spans:
        for i in range(len(cells)):
            if start <= (i + 0.5) / div < start + length and cells[i] == ".":
                cells[i] = "="
    return "".join(cells)


def _pitch_row(pitch: list, beats: int, div: int, lo: float, hi: float) -> str:
    """Vocal pitch as 0-9 within the song's vocal range (a laser-position hint)."""
    at = {round(b * 4): m for b, m in pitch}
    cells = []
    for i in range(beats * div):  # same cell-centre rule as _span_row
        m = at.get(int((i + 0.5) / div * 4))
        cells.append("." if m is None else str(int(np.clip(round((m - lo) / max(hi - lo, 1e-6) * 9), 0, 9))))
    return "".join(cells)


def _lane_row(onsets: list, pitch: list, window: list, beats: int, div: int) -> str:
    """Onsets of a pitched row as lanes A-D by pitch within the neighbouring measures (BT stairs)."""
    lo, hi = np.percentile(window, [10, 90]) if window else (0.0, 0.0)
    shown = {b for b, h in onsets if h >= 0.3}
    cells = ["."] * (beats * div)
    for b, m in pitch:
        i = int(round(b * div))
        if b in shown and 0 <= i < len(cells) and abs(b * div - i) < 1e-3:
            cells[i] = "ABCD"[int(np.clip(round((m - lo) / (hi - lo) * 3), 0, 3))] if hi - lo >= 1 else "B"
    return "".join(cells)


def to_text(a: dict) -> str:
    t = a["tempo"]
    beats = t["time_sig"][0]
    ms = a["measures"]
    stems = bool(ms) and "stems" in ms[0]
    rows = list(ms[0]["stems"]["onsets"]) if stems else []
    lanes = [r for r in LANE_ROWS if r in rows]
    names = rows + ["vpitch"] + [LANE_ROWS[r] for r in lanes] if stems else ["low", "mid", "high"]
    lines = [
        f"BPM {t['bpm']:g} (conf {t['confidence']:.2f})"
        + "".join(f" -> m{m}:{v:g}" for m, v in t.get("changes", []))
        + f"  offset {a['offset_ms']}ms  "
        f"{t['time_sig'][0]}/{t['time_sig'][1]}  duration {a['audio']['duration_sec']:.1f}s  measures 0-{len(ms) - 1}",
        "sections: " + " | ".join(f"{s['label']} m{s['start']}-{s['end'] - 1} ({s['energy']:.2f})" for s in a["sections"]),
    ]
    if stems:
        values = [p for m in ms for _, p in m["stems"]["vocal_pitch"]]
        lo, hi = (np.percentile(values, [5, 95]) if values else (60.0, 72.0))
        lines.append(f"stems: '=' = still sounding; vpitch 0-9 = vocal pitch over "
                     f"{librosa.midi_to_note(lo)}-{librosa.midi_to_note(hi)} (low = left); "
                     + ", ".join(f"{LANE_ROWS[r]} = {r}-stem note" for r in lanes) + " as lane A-D by pitch within m-1..m+1")
    lines += ["", f"{'m':<4}{'energy':<8}" + "".join(f"{n:<{beats * 4 + 1}}" for n in names)]
    for m in ms:
        triplet = sum(1 for b, _ in m["onsets"]["all"] if abs(b * 3 - round(b * 3)) < 1e-3 and abs(b * 4 - round(b * 4)) > 1e-3)
        div = 3 if triplet >= 3 else 4
        if stems:
            st = m["stems"]
            cols = [_span_row(_grid_row(st["onsets"][k], beats, div), st["sustain"].get(k, []), beats, div)
                    for k in rows]
            cols.append(_pitch_row(st["vocal_pitch"], beats, div, lo, hi))
            for r in lanes:
                near = [p for n in ms[max(0, m["index"] - 1):m["index"] + 2] for _, p in n["stems"].get(f"{r}_pitch", [])]
                cols.append(_lane_row(st["onsets"][r], st.get(f"{r}_pitch", []), near, beats, div))
        else:
            cols = [_grid_row(m["onsets"][k], beats, div) for k in ("low", "mid", "high")]
        if div == 3:
            cols = ["|".join(r[i:i + 3] for i in range(0, len(r), 3)) for r in cols]
        lines.append(f"{m['index']:<4}{m['energy']:<8.2f}" + " ".join(cols))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto analyze", description="Analyze audio for charting")
    p.add_argument("audio")
    p.add_argument("-o", "--output", help="analysis JSON path (default: stdout)")
    p.add_argument("--text", help="also write the LLM-readable text summary here")
    p.add_argument("--beats", type=int, default=4, help="beats per measure (default 4)")
    p.add_argument("--tempo", help="fixed tempo map 'MEASURE:BPM,...', e.g. 0:141,53:138.4,63:141")
    p.add_argument("--offset", type=int, help="fixed offset in ms (measure 0 start)")
    p.add_argument("--stems", help="stem directory from `ksmauto separate` (adds per-instrument rows)")
    args = p.parse_args(argv)
    tempo = [[int(m), float(b)] for m, b in (x.split(":") for x in args.tempo.split(","))] if args.tempo else None
    a = analyze(args.audio, beats_per_measure=args.beats, tempo=tempo, offset_ms=args.offset, stems=args.stems)
    js = json.dumps(a, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(js + "\n", encoding="utf-8")
    else:
        print(js)
    if args.text:
        Path(args.text).write_text(to_text(a), encoding="utf-8")
    return 0
