"""Fit ksmauto.lint.LEVEL_COEF on the official corpus (prints coefficients and errors).

Usage: uv run python tests/eval/fit_level.py
"""

from pathlib import Path

import numpy as np

from ksmauto.ksh import load_ksh
from ksmauto.lint import stats

FEATURES = ("avg_nps", "peak_nps", "laser_ratio")
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    rows, levels, names = [], [], []
    for p in sorted((ROOT / "corpus" / "official").rglob("*.ksh")):
        c = load_ksh(p)
        s = stats(c)
        rows.append([s[k] for k in FEATURES] + [1.0])
        levels.append(c["meta"]["level"])
        names.append(p.name)
    X, y = np.array(rows), np.array(levels, dtype=float)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    for n, a, b in zip(names, y, pred):
        print(f"{n:<36} level {a:>4.0f}  est {b:5.1f}")
    print("MAE", round(float(np.abs(pred - y).mean()), 2))
    print({k: round(float(v), 3) for k, v in zip(FEATURES + ("bias",), coef)})


if __name__ == "__main__":
    main()
