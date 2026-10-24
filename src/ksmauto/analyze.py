"""Audio analysis for chart authoring (see docs/analysis-format.md).

Requires the `audio` extra (numpy, scipy, librosa, soundfile).
"""

from __future__ import annotations

import json
from pathlib import Path

import librosa
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

SR = 22050
HOP = 128  # ~5.8 ms per frame
N_FFT = 1024  # short window keeps onset timing tight
BANDS = {"low": (20.0, 180.0), "mid": (180.0, 3000.0), "high": (5000.0, 11000.0)}
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


def analyze(path: str | Path, beats_per_measure: int = 4) -> dict:
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

    bpm, conf, cands = _estimate_tempo(env, fps)
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
    beat_sec = 60.0 / bpm
    measure_sec = beat_sec * beats_per_measure
    n_measures = int(np.ceil((duration - offset_sec) / measure_sec))

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]

    peaks = {}
    for name, e in list(bands.items()) + [("all", env_all)]:
        idx, props = find_peaks(e, height=0.12, distance=max(1, int(period / 4 * 0.6)))
        peaks[name] = (idx / fps, np.clip(props["peak_heights"], 0, 1))

    measures = []
    feats = []
    for m in range(n_measures):
        t0 = offset_sec + m * measure_sec
        f0, f1 = int(t0 * fps), int((t0 + measure_sec) * fps)
        seg = slice(max(0, f0), max(f0 + 1, min(f1, len(rms))))
        onsets = {}
        for name, (times, heights) in peaks.items():
            sel = (times >= t0 - beat_sec * 0.1) & (times < t0 + measure_sec - beat_sec * 0.1)
            beats = (times[sel] - t0) / beat_sec
            q = _quantize(beats)
            best: dict[float, float] = {}
            for qb, h in zip(q, heights[sel]):
                if qb is None or qb < 0 or qb >= beats_per_measure:
                    continue
                key = round(qb, 4)
                best[key] = max(best.get(key, 0.0), float(h))
            onsets[name] = [[_fmt_beat(b), round(h, 2)] for b, h in sorted(best.items())]
        measures.append({
            "index": m,
            "start_sec": round(t0, 4),
            "energy": float(rms[seg].mean()) if f0 < len(rms) else 0.0,
            "onsets": onsets,
        })
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
            "changes": [],
            "time_sig": [beats_per_measure, 4],
        },
        "offset_ms": int(round(offset_sec * 1000)),
        "measures": measures,
        "sections": sections,
    }


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


def to_text(a: dict) -> str:
    t = a["tempo"]
    beats = t["time_sig"][0]
    ms = a["measures"]
    lines = [
        f"BPM {t['bpm']:g} (conf {t['confidence']:.2f})  offset {a['offset_ms']}ms  "
        f"{t['time_sig'][0]}/{t['time_sig'][1]}  duration {a['audio']['duration_sec']:.1f}s  measures 0-{len(ms) - 1}",
        "sections: " + " | ".join(f"{s['label']} m{s['start']}-{s['end'] - 1} ({s['energy']:.2f})" for s in a["sections"]),
        "",
        f"{'m':<4}{'energy':<8}{'low':<{beats * 4 + 1}}{'mid':<{beats * 4 + 1}}{'high':<{beats * 4 + 1}}",
    ]
    for m in ms:
        triplet = sum(1 for b, _ in m["onsets"]["all"] if abs(b * 3 - round(b * 3)) < 1e-3 and abs(b * 4 - round(b * 4)) > 1e-3)
        div = 3 if triplet >= 3 else 4
        rows = [_grid_row(m["onsets"][k], beats, div) for k in ("low", "mid", "high")]
        if div == 3:
            rows = ["|".join(r[i:i + 3] for i in range(0, len(r), 3)) for r in rows]
        lines.append(f"{m['index']:<4}{m['energy']:<8.2f}" + " ".join(rows))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ksmauto analyze", description="Analyze audio for charting")
    p.add_argument("audio")
    p.add_argument("-o", "--output", help="analysis JSON path (default: stdout)")
    p.add_argument("--text", help="also write the LLM-readable text summary here")
    p.add_argument("--beats", type=int, default=4, help="beats per measure (default 4)")
    args = p.parse_args(argv)
    a = analyze(args.audio, beats_per_measure=args.beats)
    js = json.dumps(a, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(js + "\n", encoding="utf-8")
    else:
        print(js)
    if args.text:
        Path(args.text).write_text(to_text(a), encoding="utf-8")
    return 0
