"""Fit ksmauto.lint.LEVEL_COEF (prints coefficients and errors).

Uses the official KSM charts (levels 1-16) and, when present, the local sdvx.in
statistics cache written by tests/eval/sdvxin_stats.py (levels 17-20). The two
sources are weighted so that each contributes equally to the fit.

Usage: uv run python tests/eval/fit_level.py
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ksmauto.ksh import load_ksh
from ksmauto.lint import FEATURES, level_features, stats
from sdvxin_stats import usable

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "out" / "sdvxin_stats.jsonl"


def load():
    rows = []
    for p in sorted((ROOT / "corpus" / "official").rglob("*.ksh")):
        c = load_ksh(p)
        rows.append(("official", p.name, float(c["meta"]["level"]), stats(c)))
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if not usable(r):
                continue
            rows.append(("sdvxin", r["key"], r["level"], r["stats"]))
    return rows


def main() -> None:
    rows = load()
    counts = defaultdict(int)
    for src, *_ in rows:
        counts[src] += 1
    X = np.array([[level_features(s)[k] for k in FEATURES] + [1.0] for *_, s in rows])
    y = np.array([lvl for _, _, lvl, _ in rows])
    w = np.sqrt(np.array([len(rows) / (len(counts) * counts[src]) for src, *_ in rows]))
    coef, *_ = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)
    pred = np.clip(X @ coef, 1, 20)
    for src in counts:
        m = np.array([r[0] == src for r in rows])
        print(f"{src}: n={m.sum()} MAE={np.abs(pred[m] - y[m]).mean():.2f}")
    by_level = defaultdict(list)
    for (src, _, lvl, _), p in zip(rows, pred):
        by_level[int(lvl)].append(p - lvl)
    for lvl in sorted(by_level):
        e = np.array(by_level[lvl])
        print(f"  level {lvl:>2}: n={len(e):>3} bias={e.mean():+.2f} MAE={np.abs(e).mean():.2f}")
    print({k: round(float(v), 3) for k, v in zip(FEATURES + ("bias",), coef)})


if __name__ == "__main__":
    main()
